"""
Tests for TranslationMiddleware end-to-end via a FastAPI test client.
"""

from collections.abc import Awaitable, Callable
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.testclient import TestClient

from fastapi_simple_i18n.helpers import t, t_datetime
from fastapi_simple_i18n.locale import get_current_locale, set_current_locale
from fastapi_simple_i18n.manager import TranslationManager
from fastapi_simple_i18n.middleware import TranslationMiddleware
from fastapi_simple_i18n.models import TranslationEntry
from fastapi_simple_i18n.timezone import get_current_timezone


@pytest.fixture(name="client")
def client_fixture() -> TestClient:
    """
    Build a FastAPI app with the middleware and a query-based locale override.
    """
    manager = TranslationManager(builtin_locale="en")
    manager.add_entries("es", [TranslationEntry(key="Yes", value="Sí")])
    manager.add_entries("fr", [TranslationEntry(key="Yes", value="Oui")])

    app = FastAPI()

    @app.middleware("http")
    async def force_locale(request: Request, call_next: Callable[[Request], Awaitable[JSONResponse]]) -> JSONResponse:
        """
        Override the locale from a ?lang= query parameter.
        """
        lang = request.query_params.get("lang")
        if lang:
            set_current_locale(lang)
        return await call_next(request)

    app.add_middleware(TranslationMiddleware, manager=manager, default_locale="en", builtin_locale="en")

    @app.get("/")
    async def index() -> JSONResponse:
        """
        Return the resolved locale and a translated string.
        """
        return JSONResponse({"locale": get_current_locale(), "yes": str(t("Yes"))})

    return TestClient(app)


def test_accept_language_detected(client: TestClient):
    """
    The locale is negotiated from the Accept-Language header.
    """
    resp = client.get("/", headers={"Accept-Language": "es"})
    assert resp.json() == {"locale": "es", "yes": "Sí"}


def test_default_locale_when_unsupported(client: TestClient):
    """
    An unsupported header falls back to the default locale.
    """
    resp = client.get("/", headers={"Accept-Language": "de"})
    assert resp.json() == {"locale": "en", "yes": "Yes"}


def test_forced_locale_overrides_header(client: TestClient):
    """
    A ?lang= override from user middleware wins over the header.
    """
    resp = client.get("/?lang=fr", headers={"Accept-Language": "es"})
    assert resp.json() == {"locale": "fr", "yes": "Oui"}


def test_locale_not_leaked_between_requests(client: TestClient):
    """
    A forced locale in one request does not leak into the next.
    """
    client.get("/?lang=fr")
    resp = client.get("/", headers={"Accept-Language": "es"})
    assert resp.json()["locale"] == "es"


def test_locale_forced_before_the_middleware_is_discarded():
    """
    The middleware assigns the locale unconditionally, overriding an upstream one.

    This is the documented rule: forcing a locale requires code that runs
    downstream of TranslationMiddleware (user middleware registered before it,
    or a route dependency).
    """

    class ForceLocaleASGI:
        """
        Outermost ASGI app that forces a locale before the middleware runs.
        """

        def __init__(self, app: object) -> None:
            self.app = app

        async def __call__(self, scope: dict[str, object], receive: Callable[[], Awaitable[dict[str, object]]], send: Callable[[dict[str, object]], Awaitable[None]]) -> None:
            """
            Set the locale, then delegate.
            """
            set_current_locale("fr")
            await self.app(scope, receive, send)  # type: ignore[operator, no-any-return]

    manager = TranslationManager(builtin_locale="en")
    manager.add_entries("es", [TranslationEntry(key="Yes", value="Sí")])
    manager.add_entries("fr", [TranslationEntry(key="Yes", value="Oui")])

    app = FastAPI()
    app.add_middleware(TranslationMiddleware, manager=manager, default_locale="en", builtin_locale="en")

    @app.get("/")
    async def index() -> JSONResponse:
        """
        Return the resolved locale and a translated string.
        """
        return JSONResponse({"locale": get_current_locale(), "yes": str(t("Yes"))})

    client = TestClient(ForceLocaleASGI(app))
    resp = client.get("/", headers={"Accept-Language": "es"})
    assert resp.json() == {"locale": "es", "yes": "Sí"}


def test_locale_resolver_sync_overrides_header():
    """
    A synchronous ``locale_resolver`` wins over the ``Accept-Language`` header.
    """

    def resolver(request: Request) -> str | None:
        """
        Pick the locale from a ``?lang=`` query parameter.
        """
        return request.query_params.get("lang")

    manager = TranslationManager(builtin_locale="en")
    manager.add_entries("es", [TranslationEntry(key="Yes", value="Sí")])
    manager.add_entries("fr", [TranslationEntry(key="Yes", value="Oui")])

    app = FastAPI()
    app.add_middleware(
        TranslationMiddleware,
        manager=manager,
        default_locale="en",
        builtin_locale="en",
        locale_resolver=resolver,
    )

    @app.get("/")
    async def index() -> JSONResponse:
        """
        Return the resolved locale and a translated string.
        """
        return JSONResponse({"locale": get_current_locale(), "yes": str(t("Yes"))})

    client = TestClient(app)
    assert client.get("/?lang=fr", headers={"Accept-Language": "es"}).json() == {"locale": "fr", "yes": "Oui"}
    assert client.get("/?lang=es", headers={"Accept-Language": "fr"}).json() == {"locale": "es", "yes": "Sí"}


def test_locale_resolver_async_overrides_header():
    """
    An ``async`` ``locale_resolver`` is awaited and used as the request locale.
    """

    async def resolver(request: Request) -> str | None:
        """
        Read the locale from a header set by the test client.
        """
        return request.headers.get("x-lang")

    manager = TranslationManager(builtin_locale="en")
    manager.add_entries("es", [TranslationEntry(key="Yes", value="Sí")])

    app = FastAPI()
    app.add_middleware(
        TranslationMiddleware,
        manager=manager,
        default_locale="en",
        builtin_locale="en",
        locale_resolver=resolver,
    )

    @app.get("/")
    async def index() -> JSONResponse:
        """
        Return the resolved locale and a translated string.
        """
        return JSONResponse({"locale": get_current_locale(), "yes": str(t("Yes"))})

    client = TestClient(app)
    assert client.get("/", headers={"Accept-Language": "es", "x-lang": "es"}).json() == {"locale": "es", "yes": "Sí"}


def test_locale_resolver_returning_none_falls_back_to_header():
    """
    A resolver that returns ``None`` falls through to ``Accept-Language``.
    """

    def resolver(request: Request) -> str | None:  # noqa: ARG001
        """
        Decline to resolve; let the middleware use the header.
        """
        return None

    manager = TranslationManager(builtin_locale="en")
    manager.add_entries("es", [TranslationEntry(key="Yes", value="Sí")])

    app = FastAPI()
    app.add_middleware(
        TranslationMiddleware,
        manager=manager,
        default_locale="en",
        builtin_locale="en",
        locale_resolver=resolver,
    )

    @app.get("/")
    async def index() -> JSONResponse:
        """
        Return the resolved locale and a translated string.
        """
        return JSONResponse({"locale": get_current_locale(), "yes": str(t("Yes"))})

    client = TestClient(app)
    assert client.get("/", headers={"Accept-Language": "es"}).json() == {"locale": "es", "yes": "Sí"}


def test_locale_resolver_does_not_skip_user_middleware_override():
    """
    The resolver runs after the per-request reset, so a locale forced by user
    middleware registered *after* ``TranslationMiddleware`` still wins.
    """

    def resolver(request: Request) -> str | None:
        """
        Return ``es`` for everything.
        """
        return "es"

    manager = TranslationManager(builtin_locale="en")
    manager.add_entries("es", [TranslationEntry(key="Yes", value="Sí")])
    manager.add_entries("fr", [TranslationEntry(key="Yes", value="Oui")])

    app = FastAPI()

    @app.middleware("http")
    async def force_locale(request: Request, call_next: Callable[[Request], Awaitable[JSONResponse]]) -> JSONResponse:
        """
        Force ``fr`` after the translation middleware has run.
        """
        set_current_locale("fr")
        return await call_next(request)

    app.add_middleware(
        TranslationMiddleware,
        manager=manager,
        default_locale="en",
        builtin_locale="en",
        locale_resolver=resolver,
    )

    @app.get("/")
    async def index() -> JSONResponse:
        """
        Return the resolved locale and a translated string.
        """
        return JSONResponse({"locale": get_current_locale(), "yes": str(t("Yes"))})

    client = TestClient(app)
    assert client.get("/").json() == {"locale": "fr", "yes": "Oui"}


def test_timezone_resolver_sync_sets_current_timezone():
    """
    A synchronous ``timezone_resolver`` sets ``current_timezone`` for the request.
    """

    def resolver(request: Request) -> str | None:
        """
        Pull the timezone from a ``?tz=`` query parameter.
        """
        return request.query_params.get("tz")

    manager = TranslationManager(builtin_locale="en")

    app = FastAPI()
    app.add_middleware(
        TranslationMiddleware,
        manager=manager,
        default_locale="en",
        builtin_locale="en",
        timezone_resolver=resolver,
    )

    @app.get("/")
    async def index() -> JSONResponse:
        """
        Return the active timezone and a formatted datetime.
        """
        naive = datetime(2024, 1, 1, 12, 0, 0)
        return JSONResponse(
            {
                "timezone": str(get_current_timezone()),
                "rendered": t_datetime(naive, format="yyyy-MM-dd HH:mm"),
            },
        )

    client = TestClient(app)
    resp = client.get("/?tz=Europe/Madrid")
    assert resp.json() == {
        "timezone": "Europe/Madrid",
        "rendered": "2024-01-01 13:00",
    }


def test_timezone_resolver_async_sets_current_timezone():
    """
    An ``async`` ``timezone_resolver`` is awaited and sets ``current_timezone``.
    """

    async def resolver(request: Request) -> str | None:
        """
        Read the timezone from a custom request header.
        """
        return request.headers.get("x-tz")

    manager = TranslationManager(builtin_locale="en")

    app = FastAPI()
    app.add_middleware(
        TranslationMiddleware,
        manager=manager,
        default_locale="en",
        builtin_locale="en",
        timezone_resolver=resolver,
    )

    @app.get("/")
    async def index() -> JSONResponse:
        """
        Return the active timezone.
        """
        return JSONResponse({"timezone": str(get_current_timezone())})

    client = TestClient(app)
    assert client.get("/", headers={"x-tz": "Asia/Tokyo"}).json() == {"timezone": "Asia/Tokyo"}


def test_timezone_resolver_returning_none_uses_default():
    """
    A resolver that returns ``None`` falls through to ``default_timezone``.
    """

    def resolver(request: Request) -> str | None:  # noqa: ARG001
        """
        Decline to resolve.
        """
        return None

    manager = TranslationManager(builtin_locale="en")

    app = FastAPI()
    app.add_middleware(
        TranslationMiddleware,
        manager=manager,
        default_locale="en",
        builtin_locale="en",
        default_timezone="Europe/Madrid",
        timezone_resolver=resolver,
    )

    @app.get("/")
    async def index() -> JSONResponse:
        """
        Return the active timezone.
        """
        return JSONResponse({"timezone": str(get_current_timezone())})

    client = TestClient(app)
    assert client.get("/").json() == {"timezone": "Europe/Madrid"}


def test_timezone_resolver_accepts_tzinfo():
    """
    The resolver may return a ``tzinfo`` instance directly.
    """

    def resolver(request: Request) -> ZoneInfo | None:  # noqa: ARG001
        """
        Return a ``ZoneInfo`` instance for ``Asia/Tokyo``.
        """
        return ZoneInfo("Asia/Tokyo")

    manager = TranslationManager(builtin_locale="en")

    app = FastAPI()
    app.add_middleware(
        TranslationMiddleware,
        manager=manager,
        default_locale="en",
        builtin_locale="en",
        timezone_resolver=resolver,
    )

    @app.get("/")
    async def index() -> JSONResponse:
        """
        Return the active timezone.
        """
        return JSONResponse({"timezone": str(get_current_timezone())})

    client = TestClient(app)
    assert client.get("/").json() == {"timezone": "Asia/Tokyo"}


def test_timezone_resolver_exception_propagates():
    """
    An exception raised by the resolver propagates out of the middleware (and
    surfaces as a 500 from FastAPI).
    """

    def resolver(request: Request) -> str | None:  # noqa: ARG001
        """
        Raise unconditionally.
        """
        raise ValueError("resolver broken")

    manager = TranslationManager(builtin_locale="en")

    app = FastAPI()
    app.add_middleware(
        TranslationMiddleware,
        manager=manager,
        default_locale="en",
        builtin_locale="en",
        timezone_resolver=resolver,
    )

    @app.get("/")
    async def index() -> JSONResponse:
        """
        Echo endpoint, should not be reached when the resolver raises.
        """
        return JSONResponse({"ok": True})

    client = TestClient(app, raise_server_exceptions=True)
    with pytest.raises(ValueError, match="resolver broken"):
        client.get("/")


def test_timezone_does_not_leak_between_requests():
    """
    A timezone set in one request does not leak into the next.
    """

    def resolver(request: Request) -> str | None:
        """
        Read the timezone from the ``?tz=`` query parameter.
        """
        return request.query_params.get("tz")

    manager = TranslationManager(builtin_locale="en")

    app = FastAPI()
    app.add_middleware(
        TranslationMiddleware,
        manager=manager,
        default_locale="en",
        builtin_locale="en",
        timezone_resolver=resolver,
    )

    @app.get("/")
    async def index() -> JSONResponse:
        """
        Return the active timezone (``str(...)`` for ``ZoneInfo``; ``None``
        when no override is in effect).
        """
        current = get_current_timezone()
        return JSONResponse({"timezone": str(current) if current is not None else None})

    client = TestClient(app)
    assert client.get("/?tz=Europe/Madrid").json() == {"timezone": "Europe/Madrid"}
    # No ``?tz=`` on this request: the resolver returns ``None`` and the
    # default timezone (``None``) is in effect — the helper sees no override.
    assert client.get("/").json() == {"timezone": None}
