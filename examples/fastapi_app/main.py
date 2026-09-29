"""
Example FastAPI application using fastapi-simple-i18n.

Run it with::

    uvicorn examples.fastapi_app.main:app --reload

Then try:

* ``GET /`` with an ``Accept-Language: es`` header to get Spanish.
* ``GET /?lang=fr`` to force French regardless of the header.
* ``GET /cart?items=3`` to see parameterized and pluralization-style strings.
* ``GET /formats`` to see locale-aware number/date/time formatting.
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
    from the ``Accept-Language`` header, and overrides it when ``lang`` is
    present. It demonstrates using ``set_current_locale`` from user middleware.
    """
    lang = request.query_params.get("lang")
    if lang:
        set_current_locale(lang)
    return await call_next(request)


# TranslationMiddleware must be added last so it runs first (outermost).
app.add_middleware(
    TranslationMiddleware,
    manager=manager,
    default_locale="en",
    builtin_locale="en",
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
    """
    now = datetime(2026, 8, 30, 14, 30, 0)
    return JSONResponse(
        {
            "locale": get_current_locale(),
            "number": t_number(1234567.89),
            "date": t_date(now.date()),
            "date_short": t_date(now.date(), format="short"),
            "time": t_time(now.time()),
            "datetime": t_datetime(now),
        },
    )


@app.get("/page")
async def page(request: Request, name: str = "Ada", items: int = 3) -> HTMLResponse:
    """
    Render a Jinja template with the same translations the JSON routes use.

    The template calls ``t()``, the ``t`` filter and ``{% trans %}`` blocks. The
    locale is negotiated by :class:`TranslationMiddleware` and read at render
    time, so the same compiled template serves every locale.
    """
    return templates.TemplateResponse(
        request,
        "page.html",
        {
            "locale": get_current_locale(),
            "who": name,
            "item_count": items,
            "total": 1234567.89,
            "today": date(2026, 8, 30),
            "moment": datetime(2026, 8, 30, 14, 30, 0),
        },
    )
