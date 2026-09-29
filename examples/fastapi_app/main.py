"""
Example FastAPI application using fastapi-simple-i18n.

Run it with::

    uvicorn examples.fastapi_app.main:app --reload

Then try:

* ``GET /`` with an ``Accept-Language: es`` header to get Spanish.
* ``GET /?lang=fr`` to force French regardless of the header.
* ``GET /?lang=es&x-lang=fr`` shows the ``locale_resolver`` winning over the
  query override (the resolver reads the ``X-Lang`` header and runs before the
  user middleware that handles ``?lang=``).
* ``GET /cart?items=3`` to see parameterized and pluralization-style strings.
* ``GET /formats`` to see locale-aware number/date/time formatting.
* ``GET /formats?tz=Europe/Madrid`` to see ``t_datetime`` projected onto a
  different timezone for the same request.
* ``GET /time`` to see the same instant rendered in multiple timezones.
* ``GET /page?name=Ada`` to see the same translations rendered in a Jinja template.
"""

from collections.abc import Awaitable, Callable
from datetime import date, datetime

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from fastapi_simple_i18n.helpers import t, t_date, t_datetime, t_number, t_time
from fastapi_simple_i18n.locale import get_current_locale, set_current_locale
from fastapi_simple_i18n.manager import TranslationManager
from fastapi_simple_i18n.middleware import TranslationMiddleware
from fastapi_simple_i18n.timezone import get_current_timezone

from .i18n import AppTranslation
from .templating import templates

# Build the manager and register the example module's translations.
manager = TranslationManager(builtin_locale="en")
manager.register_translation(AppTranslation)

app = FastAPI(title="fastapi-simple-i18n example")


@app.middleware("http")
async def force_locale_from_query(request: Request, call_next: Callable[[Request], Awaitable[JSONResponse]]) -> JSONResponse:
    """
    Allow forcing the locale with a ``?lang=`` query parameter.

    This runs after :class:`TranslationMiddleware` has negotiated the locale
    from the ``Accept-Language`` header (or after ``locale_resolver`` has
    picked one), and overrides it when ``lang`` is present. It demonstrates
    using ``set_current_locale`` from user middleware.
    """
    lang = request.query_params.get("lang")
    if lang:
        set_current_locale(lang)
    return await call_next(request)


def locale_resolver(request: Request) -> str | None:
    """
    Pick the request locale from an ``X-Lang`` request header.

    This is wired into :class:`TranslationMiddleware` as ``locale_resolver``
    and runs before ``Accept-Language`` negotiation. It is intentionally
    separate from the ``?lang=`` query override below so the two paths can be
    exercised independently. Return ``None`` to fall through to
    ``Accept-Language``.
    """
    value = request.headers.get("x-lang")
    return value or None


def timezone_resolver(request: Request) -> str | None:
    """
    Pick the request timezone from a ``?tz=`` query parameter.

    Returned as an IANA name (``"Europe/Madrid"``, ``"Asia/Tokyo"``); the
    middleware normalizes it through :func:`resolve_timezone`. Returning
    ``None`` leaves the default timezone (``UTC`` here) in place.
    """
    return request.query_params.get("tz") or None


# TranslationMiddleware must be added last so it runs first (outermost).
app.add_middleware(
    TranslationMiddleware,
    manager=manager,
    default_locale="en",
    builtin_locale="en",
    default_timezone="UTC",
    locale_resolver=locale_resolver,
    timezone_resolver=timezone_resolver,
)


@app.get("/")
async def index() -> JSONResponse:
    """
    Return a couple of translated greetings for the resolved locale.
    """
    return JSONResponse(
        {
            "locale": get_current_locale(),
            "welcome": t("Welcome to the example app"),
            "hello": t("Hello, {name}!", name="Ada"),
            "yes": t("Yes"),
            "archive_verb": t("Archive", _variant="verb"),
            "archive_noun": t("Archive", _variant="noun"),
            "my_items_draft": t("My items"),
        },
    )


@app.get("/cart")
async def cart(items: int = 1) -> JSONResponse:
    """
    Return a parameterized, locale-aware cart summary.
    """
    return JSONResponse(
        {
            "locale": get_current_locale(),
            "summary": t("There are {item_count} items in your cart", item_count=items),
            "count": t_number(items),
        },
    )


@app.get("/formats")
async def formats() -> JSONResponse:
    """
    Return locale-aware number, date, time, and datetime formatting.

    ``datetime`` and ``time`` are rendered in two ways: against the active
    timezone (picked by ``timezone_resolver`` from the ``?tz=`` query
    parameter, ``UTC`` by default) and against ``UTC`` explicitly, so the
    same naive instant can be compared across zones in a single response.
    """
    now = datetime(2026, 8, 30, 14, 30, 0)
    current_tz = get_current_timezone()
    return JSONResponse(
        {
            "locale": get_current_locale(),
            "timezone": str(current_tz) if current_tz is not None else None,
            "number": t_number(1234567.89),
            "date": t_date(now.date()),
            "date_short": t_date(now.date(), format="short"),
            "time": t_time(now.time()),
            "time_utc": t_time(now.time(), tz="UTC"),
            "datetime": t_datetime(now),
            "datetime_utc": t_datetime(now, tz="UTC"),
        },
    )


@app.get("/time")
async def time_route() -> JSONResponse:
    """
    Render the same instant in three timezones.

    Demonstrates passing an explicit ``tz=`` to :func:`t_datetime` to override
    the active timezone for a single call. The active timezone (``?tz=`` or
    the default) is also included so the contrast is visible in the response.
    """
    moment = datetime(2026, 8, 30, 14, 30, 0)
    active = get_current_timezone()
    return JSONResponse(
        {
            "locale": get_current_locale(),
            "active_timezone": str(active) if active is not None else None,
            "as_utc": t_datetime(moment, tz="UTC"),
            "as_madrid": t_datetime(moment, tz="Europe/Madrid"),
            "as_tokyo": t_datetime(moment, tz="Asia/Tokyo"),
            "in_active": t_datetime(moment),
        },
    )


@app.get("/page")
async def page(request: Request, name: str = "Ada", items: int = 3) -> HTMLResponse:
    """
    Render a Jinja template with the same translations the JSON routes use.

    The template calls ``t()``, the ``t`` filter and ``{% trans %}`` blocks. The
    locale is negotiated by :class:`TranslationMiddleware` and read at render
    time, so the same compiled template serves every locale. ``t_datetime`` is
    also called so the active timezone (set by the ``?tz=`` resolver) shows up
    in the rendered page.
    """
    return templates.TemplateResponse(
        request,
        "page.html",
        {
            "locale": get_current_locale(),
            "timezone": str(get_current_timezone()) if get_current_timezone() is not None else "UTC",
            "who": name,
            "item_count": items,
            "total": 1234567.89,
            "today": date(2026, 8, 30),
            "moment": datetime(2026, 8, 30, 14, 30, 0),
        },
    )
