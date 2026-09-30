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

`t()` returns a `str` subclass carrying the translated text, so it works
directly in a JSON response — no `str()` needed:

```python
@app.get("/")
async def index() -> dict[str, str]:
    return {
        "welcome": t("Welcome to the example app"),
        "hello": t("Hello, {name}!", name="Ada"),
        "archive": t("Archive", _variant="noun"),
    }
```

`get_current_locale()` returns a `babel.core.Locale`, which is not a string, so
wrap it where a string is what the response needs:

```python
@app.get("/locale")
async def locale() -> dict[str, str]:
    return {"locale": str(get_current_locale())}
```

That yields `{"locale": "es_ES"}` for a request asking for `es-ES`. When you
want a subtag rather than the whole identifier, use the object:

```python
current = get_current_locale()
current.language      # "es"
current.territory     # "ES", or None
```

### Capturing a value before the locale is known

`t()` translates now, which is what an endpoint body wants. When a value is
captured earlier — a module-level constant, a message attached to a task that
will be rendered later — use `lazy_t()` instead and let it translate at render
time:

```python
from fastapi_simple_i18n.helpers import lazy_t

GREETING = lazy_t("Welcome back")
```

`lazy_t()` returns a `LazyTranslatableStr`, which is **not** a `str`, so it
needs an explicit `str()` at the boundaries that go through the C-level string
protocol: `json.dumps`, a Pydantic str field, `urllib.parse.quote`. In a Jinja
template it needs nothing, because the environment renders it through `str()`
(see [Templates](jinja.md)).

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

`set_current_locale` accepts any spelling of a locale and validates it, so a
`?lang=whatever` from a user raises a `ValueError` (a 500) instead of silently
serving an untranslated page. Ignore or convert the error there if that is not
what you want:

```python
    try:
        set_current_locale(lang)
    except ValueError:
        pass  # unknown locale: keep the negotiated one
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

## Formatting numbers, dates, times and amounts

The Babel-backed helpers use the current locale automatically:

```python
from datetime import datetime

from fastapi_simple_i18n.helpers import t_amount, t_date, t_datetime, t_money, t_number, t_time

t_number(1234567.89)           # "1,234,567.89" (en) / "1.234.567,89" (es)
t_money(1234567.89, "EUR")     # "€1,234,567.89" (en) / "1.234.567,89 €" (es)
t_amount(1234567.89)           # "1,234,567.89" (en) / "1.234.567,89" (es)
t_date(datetime.now().date())  # "Aug 30, 2026" (en) / "30 ago 2026" (es)
t_time(datetime.now().time())
t_datetime(datetime.now())
```

`t_money` takes an ISO currency code (case-insensitive) and `t_amount` is the
same without a symbol, for sums that mix currencies. A blank or unrecognised
currency code renders a plain localized decimal and logs a warning, so a bad
code never breaks a rendered page.

Each helper accepts an optional `format` (`"short"`, `"medium"`, `"long"`,
`"full"`, or a custom Babel pattern) and an explicit `locale` override
(any spelling, or a `Locale`). `t_time` and `t_datetime` also accept a `tz`
override, which is resolved on every call.

## Timezones per request

There is always a timezone in effect. It starts at `UTC` — not at the server's
local zone, which has nothing to do with the user a response is written for —
and `TranslationMiddleware` resolves a per-request one on top of that:

```python
app.add_middleware(
    TranslationMiddleware,
    manager=manager,
    default_locale="en",
    default_timezone="UTC",
    timezone_resolver=lambda request: request.query_params.get("tz"),
)
```

`timezone_resolver` may be sync or async, and may return an IANA name or a
`tzinfo`. Returning `None` keeps the default. See the `timezone_resolver` in
the example app.

```python
from fastapi_simple_i18n.timezone import get_current_timezone

get_current_timezone()   # always a tzinfo, never None
```

A `default_timezone` or a resolver result that is not a usable timezone is
reported where it was written — when the middleware stack is built, or on the
request that produced it — instead of quietly falling back. `None` is not an
option for either, because there is no missing-timezone state to fall back to:

```python
app.add_middleware(TranslationMiddleware, manager=manager, default_timezone=None)
# TypeError: Invalid timezone None: expected a timezone string, got NoneType
```
