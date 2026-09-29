# Usage in FastAPI

## Adding the middleware

Build a manager, register your translations, and add `TranslationMiddleware`:

```python
from fastapi import FastAPI

from fastapi_simple_i18n.helpers import t
from fastapi_simple_i18n.locale import get_current_locale
from fastapi_simple_i18n.manager import TranslationManager
from fastapi_simple_i18n.middleware import TranslationMiddleware

from myapp.i18n import AppTranslation

manager = TranslationManager(builtin_locale="en")
manager.register_translation(AppTranslation)

app = FastAPI()
app.add_middleware(
    TranslationMiddleware,
    manager=manager,
    default_locale="en",
    builtin_locale="en",
)
```

This is the only module that needs Starlette, so install the `fastapi` extra
(`uv add "fastapi-simple-i18n[fastapi] @ git+https://github.com/okelet/fastapi-simple-i18n"`).

The middleware does three things:

* Registers the manager as the active one, so `t()` works everywhere.
* Applies the `default_locale` process-wide.
* Negotiates the request locale from the `Accept-Language` header against the
  manager's supported locales.

It also resets `current_locale` at the start of every request, so a value left
behind by a previous request cannot leak into the next one. It then negotiates
and assigns the locale **unconditionally**, so `TranslationMiddleware` always
overrides a locale that was already set for the same request.

## Translating in endpoints

`t()` returns a lazy object; call `str()` on it (or let your template engine do
so) to render:

```python
@app.get("/")
async def index() -> dict[str, str]:
    return {
        "locale": get_current_locale(),
        "welcome": str(t("Welcome to the example app")),
        "hello": str(t("Hello, {name}!", name="Ada")),
        "archive": str(t("Archive", _variant="noun")),
    }
```

## Forcing the locale from your own middleware

Because the locale lives in a `ContextVar`, any user middleware can override it
with `set_current_locale`. This is the recommended way to honor a per-user
preference or a query parameter:

```python
from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import Response

from fastapi_simple_i18n.locale import set_current_locale


@app.middleware("http")
async def force_locale(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    lang = request.query_params.get("lang")
    if lang:
        set_current_locale(lang)
    return await call_next(request)
```

!!! warning
    Register `TranslationMiddleware` **last** (with `add_middleware`), after
    `force_locale`.

    Starlette runs middlewares in reverse registration order, so the last one
    registered is the outermost and runs first. `TranslationMiddleware`
    negotiates and assigns the locale before calling anything downstream, so a
    locale forced in a middleware registered *after* it would be overwritten.

    The same applies to a route dependency: it runs downstream of the
    middleware, so forcing the locale there works too.

## Formatting numbers, dates, and times

The Babel-backed helpers use the current locale automatically:

```python
from datetime import datetime

from fastapi_simple_i18n.helpers import t_number, t_date, t_time, t_datetime

t_number(1234567.89)          # "1,234,567.89" (en) / "1.234.567,89" (es)
t_date(datetime.now().date()) # "Aug 30, 2026" (en) / "30 ago 2026" (es)
t_time(datetime.now().time())
t_datetime(datetime.now())
```

Each accepts an optional `format` (`"short"`, `"medium"`, `"long"`, `"full"`, or
a custom Babel pattern) and an explicit `locale` override.
