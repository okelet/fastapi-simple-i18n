"""
Starlette/FastAPI middleware for per-request locale detection.

The middleware wires a :class:`~fastapi_simple_i18n.manager.TranslationManager`
into the request context, configures the default locale, and detects the
request locale from the ``Accept-Language`` header.

It negotiates a locale for every request and sets it unconditionally, so a
locale forced earlier in the same context is overwritten and not respected. To
force a locale (a per-user preference, a query parameter) instead, set it with
:func:`~fastapi_simple_i18n.locale.set_current_locale` in code that runs *after*
this middleware, such as a user middleware registered before it with
``add_middleware`` or a route dependency.

This is the only module that depends on Starlette, which ships as the optional
``fastapi`` extra (``pip install fastapi-simple-i18n[fastapi]``).
"""

from collections.abc import Awaitable, Callable

try:
    from starlette.requests import Request
    from starlette.types import ASGIApp
except ImportError as exc:  # pragma: no cover - depends on the install extras
    raise ImportError(
        "TranslationMiddleware requires Starlette. Install the optional extra with "
        "'pip install fastapi-simple-i18n[fastapi]' (or add 'starlette' to your project)."
    ) from exc

from .locale import current_locale, set_current_locale, set_default_locale
from .manager import TranslationManager
from .negotiation import negotiate_locale
from .registry import set_translation_manager


class TranslationMiddleware:
    """
    Middleware that resolves and sets the locale for each request.

    Args:
        app: The wrapped ASGI application.
        manager: The translation manager to activate for the process.
        default_locale: Locale used when the request locale cannot be resolved
            from the request itself.
        builtin_locale: The built-in locale (the language the source strings are
            written in). This is applied to the manager. Defaults to ``"en"``.

    Behavior:

    * The manager is registered globally so ``t()`` works everywhere.
    * The default locale is applied process-wide.
    * ``current_locale`` is reset to empty for every request, discarding any
      value inherited from an earlier one.
    * The ``Accept-Language`` header is negotiated against the manager's
      supported locales and the result is set unconditionally for the request.
      Because the assignment is unconditional, a locale forced before this
      middleware ran is overwritten, not respected.
    * To force a locale instead, register user middleware or a dependency that
      runs after this one (add ``TranslationMiddleware`` last).
    """

    def __init__(
        self,
        app: ASGIApp,
        manager: TranslationManager,
        default_locale: str = "en",
        builtin_locale: str = "en",
    ) -> None:
        """
        Configure the middleware and register the manager globally.
        """
        self.app = app
        self.manager = manager
        self.default_locale = default_locale
        self.manager.builtin_locale = builtin_locale
        set_translation_manager(manager)
        set_default_locale(default_locale)

    async def __call__(
        self,
        scope: dict[str, object],
        receive: Callable[[], Awaitable[dict[str, object]]],
        send: Callable[[dict[str, object]], Awaitable[None]],
    ) -> None:
        """
        Resolve the locale for the incoming request and delegate downstream.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Discard any value inherited from an earlier request.
        current_locale.set("")

        request = Request(scope, receive)
        accept_language = request.headers.get("accept-language", "")
        resolved = negotiate_locale(
            accept_language,
            self.manager.supported_locales(),
            self.default_locale,
        )
        set_current_locale(resolved)

        await self.app(scope, receive, send)
