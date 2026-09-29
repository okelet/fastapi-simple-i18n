r"""
FastAPI application for the translation file web UI.

Run it from the repository root after a single sync::

    uv sync --group web
    FSI_WEB_TRANSLATIONS_DIR=/path/to/translations \\
        uv run --group web uvicorn fastapi_simple_i18n.web.app:app

The UI reads and writes the locale JSON files directly: there is no second
database to import into and no migration to run. The router keeps the
filesystem out of the request handlers by going through the pure helpers in
:mod:`fastapi_simple_i18n.web.catalog` and the atomic writes in
:mod:`fastapi_simple_i18n.web.storage`.
"""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .catalog import (
    EntryFilter,
    EntryRow,
    UnknownLocaleError,
    collect_variants,
    filter_rows,
    list_locales,
    load_catalog,
    paginate,
    placeholder_issues,
)
from .config import Settings, get_settings
from .storage import EntryWriteError, create_entry, delete_entry, update_entry

logger = logging.getLogger(__name__)

# ``Path(__file__).parent / "templates"`` is the Jinja search root, with a
# shared base, one shell per page and a ``partials/`` directory for HTMX
# fragments. Templates are picked up at import time; static assets are served
# from the sibling ``static/`` directory.
TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

# The variant multiselect reserves the empty-string value for "no variant": it
# is a value the URL can carry unambiguously and one that maps cleanly to the
# optional ``variant`` field on the model.
NO_VARIANT_OPTION = ""


def _build_templates(directory: Path = TEMPLATES_DIR) -> Jinja2Templates:
    """
    Return a Jinja2 environment wired up with the globals every page imports.

    Args:
        directory: Templates directory to use.

    Returns:
        A configured ``Jinja2Templates`` instance.
    """
    templates = Jinja2Templates(directory=str(directory))
    templates.env.globals.update(
        {
            "format_bytes": _format_bytes,
            "format_modified": _format_modified,
            "placeholder_issues": placeholder_issues,
            "no_variant_option": NO_VARIANT_OPTION,
        }
    )
    return templates


def _format_bytes(size: int) -> str:
    """
    Render a byte count with a human-friendly suffix.
    """
    if size < 1024:
        return f"{size} B"
    units = ("KB", "MB", "GB")
    value = float(size) / 1024
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"  # pragma: no cover - loop always returns


def _format_modified(moment: object) -> str:
    """
    Render an mtime in a single, unambiguous local format.

    Returning ISO-style ``"YYYY-MM-DD HH:MM"`` sidesteps locale-dependent
    parsing while staying short enough for a table cell.
    """
    if moment is None:
        return "—"
    return moment.strftime("%Y-%m-%d %H:%M")  # type: ignore[attr-defined]


def _is_htmx(request: Request) -> bool:
    """
    Whether the request comes from an HTMX-driven form.

    Non-HTMX submits are answered with a redirect and a flash message so the
    page reloads with the change applied; HTMX submits are answered with the
    fragment the caller asked for.
    """
    return request.headers.get("hx-request") == "true"


def _settings_or(settings: Settings | None) -> Settings:
    """
    Return ``settings`` if it was supplied, otherwise the cached singleton.

    Spelled out so :func:`create_app` reads naturally in both the ``create_app()``
    convenience path and the test suite, which usually wants to pass its own
    settings instance.
    """
    return settings or get_settings()


def _clean_variant(variant: str | None) -> str | None:
    """
    Normalise the variant input: empty string and whitespace-only become ``None``.
    """
    if variant is None:
        return None
    cleaned = variant.strip()
    return cleaned or None


def _strings_context(
    directory: Path,
    cfg: Settings,
    request: Request,
    locale: str,
    q: str,
    variant: list[str],
    draft: str,
    page: int,
) -> dict[str, object]:
    """
    Build the context shared by the strings page shell and its HTMX fragment.

    Args:
        directory: Directory holding the locale files.
        cfg: Settings.
        request: The incoming HTTP request.
        locale: Locale to read.
        q: Free-text query.
        variant: Selected variant options.
        draft: Draft tri-state filter.
        page: 1-based page number.

    Returns:
        A context dict suitable for both ``strings.html`` and
        ``partials/_results.html``.
    """
    entry_filter = EntryFilter(text=q, variants=tuple(variant), draft=draft)
    try:
        catalog = load_catalog(directory, locale)
    except UnknownLocaleError:
        raise HTTPException(status_code=404, detail="Unknown locale.") from None
    # ``load_catalog`` returns a catalog with an error message instead of
    # raising on a missing or malformed file; the page must not pretend to
    # have entries it does not have, so treat it the same as a 404.
    if not catalog.is_readable:
        raise HTTPException(status_code=404, detail=catalog.error or "Locale not available.") from None
    rows = filter_rows(list(catalog.rows), entry_filter)
    entries_page = paginate(rows, page, cfg.page_size, entry_filter)
    return {
        "request": request,
        "site_title": cfg.site_title,
        "directory": directory,
        "locale": catalog.locale,
        "display_name": catalog.display_name,
        "flag": catalog.flag,
        "file_name": catalog.file_name,
        "all_variants": collect_variants(directory),
        "drafts": catalog.draft_count,
        "empty_count": sum(1 for row in catalog.rows if row.is_empty),
        "total": catalog.entry_count,
        "filter": entry_filter,
        "page": entries_page,
    }


def _json_triggers(payload: dict[str, object]) -> str:
    """
    JSON-encode an HTMX trigger header in one place so all routes share the format.

    Args:
        payload: Mapping of trigger name to detail.

    Returns:
        A JSON string with no whitespace (HTMX expects compact JSON).
    """
    return json.dumps(payload, separators=(",", ":"))


def _toast_redirect(request: Request, locale: str, message: str, toast_type: str) -> RedirectResponse:
    """
    Build a redirect that surfaces a flash message via the URL.

    Args:
        request: The incoming HTTP request.
        locale: Locale to redirect to.
        message: Flash message text.
        toast_type: Either ``"success"`` or ``"error"``.

    Returns:
        A 303 redirect to the locale's strings page.
    """
    target = request.url_for("locale_strings", locale=locale)
    separator = "&" if "?" in str(target) else "?"
    return RedirectResponse(url=f"{target}{separator}toast={message}&toast_type={toast_type}", status_code=303)


def _success_response(request: Request, locale: str, message: str) -> Response:
    """
    Build the success response for create and update.

    HTMX callers get an empty body and trigger headers; plain form submits get
    a redirect with a flash toast.

    Args:
        request: The incoming HTTP request.
        locale: Locale to redirect to.
        message: Flash message text.

    Returns:
        An HTMX response (204 + triggers) or a redirect.
    """
    if _is_htmx(request):
        return Response(
            status_code=204,
            headers={"HX-Trigger": _json_triggers({"close-entry-dialog": True, "strings-refresh": True, "toast": {"message": message, "type": "success"}})},
        )
    return _toast_redirect(request, locale, message, "success")


def _error_response(request: Request, locale: str, message: str) -> Response:
    """
    Surface a flash message about a failed action.

    Args:
        request: The incoming HTTP request.
        locale: Locale to redirect to.
        message: Flash message text.

    Returns:
        An HTMX response or a redirect.
    """
    if _is_htmx(request):
        return Response(status_code=204, headers={"HX-Trigger": _json_triggers({"toast": {"message": message, "type": "error"}})})
    return _toast_redirect(request, locale, message, "error")


def _update_form_error(
    request: Request,
    templates: Jinja2Templates,
    directory: Path,
    locale: str,
    index: int,
    exc: EntryWriteError,
) -> Response:
    """
    Render the edit form back into the dialog with an inline error.

    Args:
        request: The incoming HTTP request.
        templates: Configured Jinja2 environment.
        directory: Directory holding the locale files.
        locale: File stem being edited.
        index: Position of the entry in the file.
        exc: Validation error raised by the write.

    Returns:
        A 422 response carrying the re-rendered form.
    """
    catalog = load_catalog(directory, locale)
    row = catalog.rows[index] if catalog.is_readable and 0 <= index < catalog.entry_count else None
    context = {
        "request": request,
        "locale": catalog.locale,
        "display_name": catalog.display_name,
        "flag": catalog.flag,
        "all_variants": collect_variants(directory),
        "mode": "update",
        "row": row,
        "error": str(exc),
    }
    body = templates.get_template("partials/_entry_form.html").render(context)
    return Response(content=body, status_code=422, media_type="text/html")


def _create_form_error(
    request: Request,
    templates: Jinja2Templates,
    directory: Path,
    locale: str,
    key: str,
    value: str,
    variant: str,
    draft: bool,
    exc: EntryWriteError,
) -> Response:
    """
    Render the create form back into the dialog with an inline error.

    Args:
        request: The incoming HTTP request.
        templates: Configured Jinja2 environment.
        directory: Directory holding the locale files.
        locale: File stem being edited.
        key: The submitted source string.
        value: The submitted translation.
        variant: The submitted variant.
        draft: The submitted draft flag.
        exc: Validation error raised by the write.

    Returns:
        A 422 response carrying the re-rendered form.
    """
    catalog = load_catalog(directory, locale)
    context = {
        "request": request,
        "locale": catalog.locale,
        "display_name": catalog.display_name,
        "flag": catalog.flag,
        "all_variants": collect_variants(directory),
        "mode": "create",
        # Echo the submitted values so the user does not lose what they typed.
        "row": EntryRow(index=0, key=key, value=value, variant=_clean_variant(variant), draft=draft),
        "error": str(exc),
    }
    body = templates.get_template("partials/_entry_form.html").render(context)
    return Response(content=body, status_code=422, media_type="text/html")


def create_app(settings: Settings | None = None) -> FastAPI:
    """
    Build the FastAPI app, sharing one ``Settings`` instance across handlers.

    A ``lifespan`` warns (without raising) when the configured directory does
    not exist yet; the locales page surfaces the same fact in the UI, so a
    fresh checkout tells the user what to do instead of refusing to start.

    Args:
        settings: Pre-configured settings, primarily for the test suite. The
            ``uvicorn`` entry point constructs the app from the environment
            and may leave this as ``None``.

    Returns:
        A fully configured FastAPI instance ready to be served.
    """
    cfg = _settings_or(settings)
    templates = _build_templates()
    directory: Path = cfg.translations_dir

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """
        Warn on startup if the configured directory is missing.
        """
        if not directory.is_dir():
            logger.warning("Translations directory %s does not exist yet; the UI will show an error.", directory)
        yield

    application = FastAPI(title=cfg.site_title, docs_url=None, redoc_url=None, lifespan=lifespan)
    # Expose the resolved settings so the test suite (and any introspection
    # tooling) can read back what the app was built with.
    application.state.settings = cfg
    # Static assets ship as plain files next to the templates; mounting once is
    # enough for the lifetime of the process.
    if STATIC_DIR.is_dir():
        application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @application.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        """
        Render the locales index.
        """
        summaries = list_locales(directory)
        context = {
            "request": request,
            "site_title": cfg.site_title,
            "directory": directory,
            "locales": summaries,
            "directory_exists": directory.is_dir(),
        }
        return templates.TemplateResponse(request, "locales.html", context)

    @application.get("/locales/{locale}", response_class=HTMLResponse)
    def locale_strings(
        request: Request,
        locale: str,
        q: str = Query(""),  # noqa: B008 - FastAPI requires the Query sentinel as a default
        variant: list[str] = Query(default_factory=list),  # noqa: B008
        draft: str = Query(""),  # noqa: B008 - FastAPI requires the Query sentinel as a default
        page: int = Query(1),  # noqa: B008 - FastAPI requires the Query sentinel as a default
    ) -> HTMLResponse:
        """
        Render the strings page shell.

        Filtering is server-side and the search form posts to
        :func:`strings_fragment`, so this route is the full shell only.
        """
        context = _strings_context(directory, cfg, request, locale, q, variant, draft, page)
        return templates.TemplateResponse(request, "strings.html", context)

    @application.get("/locales/{locale}/strings", response_class=HTMLResponse)
    def strings_fragment(
        request: Request,
        locale: str,
        q: str = Query(""),  # noqa: B008 - FastAPI requires the Query sentinel as a default
        variant: list[str] = Query(default_factory=list),  # noqa: B008
        draft: str = Query(""),  # noqa: B008 - FastAPI requires the Query sentinel as a default
        page: int = Query(1),  # noqa: B008 - FastAPI requires the Query sentinel as a default
    ) -> HTMLResponse:
        """
        Render just the results fragment swapped in by the search form.
        """
        context = _strings_context(directory, cfg, request, locale, q, variant, draft, page)
        return templates.TemplateResponse(request, "partials/_results.html", context)

    @application.get("/locales/{locale}/entry", response_class=HTMLResponse)
    def edit_form(
        request: Request,
        locale: str,
        index: int = Query(...),
    ) -> HTMLResponse:
        """
        Render the edit dialog body for one existing entry.

        The dialog wrapper itself lives in ``base.html``; this endpoint only
        fills its body. HTMX swaps the response into ``#entry-form``.
        """
        try:
            catalog = load_catalog(directory, locale)
        except UnknownLocaleError:
            raise HTTPException(status_code=404, detail="Unknown locale.") from None
        if not catalog.is_readable:
            return templates.TemplateResponse(request, "partials/_entry_form.html", {"request": request, "locale": catalog.locale, "display_name": catalog.display_name, "flag": catalog.flag, "all_variants": collect_variants(directory), "mode": "update", "row": None, "error": catalog.error})
        if not 0 <= index < catalog.entry_count:
            raise HTTPException(status_code=404, detail="Entry not found.") from None
        row: EntryRow = catalog.rows[index]
        context = {
            "request": request,
            "locale": catalog.locale,
            "display_name": catalog.display_name,
            "flag": catalog.flag,
            "all_variants": collect_variants(directory),
            "mode": "update",
            "row": row,
            "error": None,
        }
        return templates.TemplateResponse(request, "partials/_entry_form.html", context)

    @application.get("/locales/{locale}/entry/new", response_class=HTMLResponse)
    def new_form(request: Request, locale: str) -> HTMLResponse:
        """
        Render the dialog body in "create" mode.
        """
        try:
            catalog = load_catalog(directory, locale)
        except UnknownLocaleError:
            raise HTTPException(status_code=404, detail="Unknown locale.") from None
        context = {
            "request": request,
            "locale": catalog.locale,
            "display_name": catalog.display_name,
            "flag": catalog.flag,
            "all_variants": collect_variants(directory),
            "mode": "create",
            "row": None,
            "error": None,
        }
        return templates.TemplateResponse(request, "partials/_entry_form.html", context)

    @application.post("/locales/{locale}/entry")
    def save_entry(
        request: Request,
        locale: str,
        index: int = Form(...),
        value: str = Form(""),
        variant: str = Form(""),
        draft: str = Form(""),
    ) -> Response:
        """
        Apply an edit, validate, persist and refresh the table.

        On success: HTMX receives an empty body and ``HX-Trigger`` headers that
        close the dialog, refresh the strings table and raise a toast; a plain
        HTML submit redirects to the strings page with a flash message.

        On validation failure: the form fragment is re-rendered with the error
        and returned with HTTP 422 so HTMX's opt-in handler shows it inline.

        Args:
            request: The incoming HTTP request.
            locale: Locale whose file is being edited.
            index: Position of the entry in the file.
            value: New translation.
            variant: New variant, or empty for none.
            draft: ``"on"`` when the checkbox is checked.

        Returns:
            Either an empty response with trigger headers (HTMX), the re-rendered
            form (HTMX, on validation failure) or a redirect (non-HTMX).
        """
        try:
            update_entry(directory, locale, index, value, _clean_variant(variant), draft == "on")
        except EntryWriteError as exc:
            return _update_form_error(request, templates, directory, locale, index, exc)
        return _success_response(request, locale, "Saved.")

    @application.post("/locales/{locale}/entry/new")
    def create_entry_route(
        request: Request,
        locale: str,
        key: str = Form(""),
        value: str = Form(""),
        variant: str = Form(""),
        draft: str = Form(""),
    ) -> Response:
        """
        Append a new entry to a locale file.

        Args:
            request: The incoming HTTP request.
            locale: Locale whose file is being edited.
            key: Source string.
            value: Translation.
            variant: New variant, or empty for none.
            draft: ``"on"`` when the checkbox is checked.

        Returns:
            Either an empty response with trigger headers (HTMX), the re-rendered
            create form (HTMX, on validation failure) or a redirect (non-HTMX).
        """
        try:
            create_entry(directory, locale, key, value, _clean_variant(variant), draft == "on")
        except EntryWriteError as exc:
            return _create_form_error(request, templates, directory, locale, key, value, variant, draft == "on", exc)
        return _success_response(request, locale, "Entry added.")

    @application.post("/locales/{locale}/entry/delete")
    def delete_entry_route(
        request: Request,
        locale: str,
        index: int = Form(...),
    ) -> Response:
        """
        Remove an entry from a locale file.

        Args:
            request: The incoming HTTP request.
            locale: Locale whose file is being edited.
            index: Position of the entry in the file.

        Returns:
            Either an empty response with trigger headers (HTMX) or a redirect
            (non-HTMX).
        """
        try:
            delete_entry(directory, locale, index)
        except EntryWriteError as exc:
            return _error_response(request, locale, str(exc))
        if _is_htmx(request):
            return Response(status_code=204, headers={"HX-Trigger": _json_triggers({"strings-refresh": True, "toast": {"message": "Entry deleted.", "type": "success"}})})
        return _toast_redirect(request, locale, "Entry deleted.", "success")

    @application.get("/health", include_in_schema=False)
    @application.get("/healthz", include_in_schema=False)
    def health() -> JSONResponse:
        """
        Liveness check for monitoring and container probes.

        Served under both ``/health`` (the conventional path most monitors
        hit by default) and ``/healthz`` (Kubernetes' liveness/readiness
        probe path).
        """
        ok = directory.is_dir() and bool(list_locales(directory))
        return JSONResponse({"status": "ok" if ok else "no-translations", "directory": str(directory)})

    return application


# Module-level instance so ``uvicorn fastapi_simple_i18n.web.app:app`` works
# out of the box. ``create_app`` accepts an explicit ``Settings`` for tests.
app: FastAPI = create_app()
