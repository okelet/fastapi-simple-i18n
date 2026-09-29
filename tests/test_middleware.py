"""
Tests for TranslationMiddleware end-to-end via a FastAPI test client.
"""

from collections.abc import Awaitable, Callable

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.testclient import TestClient

from fastapi_simple_i18n.helpers import t
from fastapi_simple_i18n.locale import get_current_locale, set_current_locale
from fastapi_simple_i18n.manager import TranslationManager
from fastapi_simple_i18n.middleware import TranslationMiddleware
from fastapi_simple_i18n.models import TranslationEntry


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
