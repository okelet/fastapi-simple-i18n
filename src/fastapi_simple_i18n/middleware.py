"""
Starlette/FastAPI middleware for per-request locale and timezone detection.

The middleware wires a :class:`~fastapi_simple_i18n.manager.TranslationManager`
into the request context, configures the default locale and timezone, detects
the request locale from the ``Accept-Language`` header, and resolves the
request timezone (when a resolver is configured).

It negotiates a locale for every request and sets it unconditionally, so a
locale forced earlier in the same context is overwritten and not respected. To
force a locale (a per-user preference, a query parameter) instead, set it with
:func:`~fastapi_simple_i18n.locale.set_current_locale` in code that runs *after*
this middleware, such as a user middleware registered before it with
``add_middleware`` or a route dependency.

Both the locale and the timezone can be resolved dynamically through
callables (``locale_resolver`` / ``timezone_resolver``). A resolver is invoked
with the current :class:`~starlette.requests.Request` and may be a regular
function or an ``async`` function; whatever it returns (an ``awaitable`` is
awaited) is used as the value. Returning ``None`` falls through to the built-in
flow (``Accept-Language`` → ``default_locale`` for the locale, no override
for the timezone).

This is the only module that depends on Starlette, which ships as the optional
``fastapi`` extra (``pip install fastapi-simple-i18n[fastapi]``).
"""

import inspect
from collections.abc import Awaitable, Callable
from datetime import tzinfo
from typing import Any

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
from .timezone import current_timezone, resolve_timezone, set_current_timezone, set_default_timezone

# A resolver is anything that takes a Request and returns either a value or an
# awaitable resolving to one (or ``None``). The middleware awaits the result
# transparently so callers can pass either a regular function or an ``async``
# one.
LocaleResolver = Callable[[Request], str | None | Awaitable[str | None]]
TimezoneResolver = Callable[[Request], tzinfo | str | None | Awaitable[tzinfo | str | None]]


async def _maybe_await(value: Any) -> Any:
    """
    Await ``value`` if it is awaitable, otherwise return it.

    Lets the middleware accept resolvers that are either plain callables or
    ``async`` callables without forcing callers to pick one.
    """
    if inspect.isawaitable(value):
        return await value
    return value


class TranslationMiddleware:
    """
    Middleware that resolves and sets the locale (and, optionally, the timezone) for each request.

    Args:
        app: The wrapped ASGI application.
        manager: The translation manager to activate for the process.
        default_locale: Locale used when the request locale cannot be resolved
            from the request itself.
        builtin_locale: The built-in locale (the language the source strings are
            written in). This is applied to the manager. Defaults to ``"en"``.
        default_timezone: Timezone used when no ``timezone_resolver`` is
            configured, or when it returns ``None``. Defaults to ``None``,
            which lets the date/time helpers use the process local zone.
        locale_resolver: Optional callable (``sync`` or ``async``) invoked with
            the incoming :class:`~starlette.requests.Request`. A non-``None``
            return value is used as the request locale, skipping
            ``Accept-Language`` negotiation. ``None`` falls through to the
            built-in flow.
        timezone_resolver: Optional callable (``sync`` or ``async``) invoked
            with the incoming :class:`~starlette.requests.Request`. A
            non-``None`` return value (a ``tzinfo`` or an IANA name) is set as
            the request timezone via
            :func:`~fastapi_simple_i18n.timezone.set_current_timezone`.
            ``None`` leaves the timezone at the default.

    Behavior:

    * The manager is registered globally so ``t()`` works everywhere.
    * The default locale and default timezone are applied process-wide.
    * ``current_locale`` and ``current_timezone`` are reset to their no-value
      state for every request, discarding any value inherited from an
      earlier one.
    * ``locale_resolver`` runs first. If it returns a locale, that value wins
      (no ``Accept-Language`` negotiation). Otherwise the ``Accept-Language``
      header is negotiated against the manager's supported locales and the
      result is set unconditionally for the request. Because the assignment
      is unconditional, a locale forced before this middleware ran is
      overwritten, not respected.
    * ``timezone_resolver`` runs after the locale and, if it returns a value,
      it is stored in ``current_timezone`` for the request.
    * To force a locale instead, register user middleware or a dependency that
      runs after this one (add ``TranslationMiddleware`` last).
    """

    def __init__(
        self,
        app: ASGIApp,
        manager: TranslationManager,
        default_locale: str = "en",
        builtin_locale: str = "en",
        default_timezone: tzinfo | str | None = None,
        locale_resolver: LocaleResolver | None = None,
        timezone_resolver: TimezoneResolver | None = None,
    ) -> None:
        """
        Configure the middleware and register the manager globally.
        """
        self.app = app
        self.manager = manager
        self.default_locale = default_locale
        self.default_timezone = default_timezone
        self.locale_resolver = locale_resolver
        self.timezone_resolver = timezone_resolver
        self.manager.builtin_locale = builtin_locale
        set_translation_manager(manager)
        set_default_locale(default_locale)
        set_default_timezone(default_timezone)

    async def __call__(
        self,
        scope: dict[str, object],
        receive: Callable[[], Awaitable[dict[str, object]]],
        send: Callable[[dict[str, object]], Awaitable[None]],
    ) -> None:
        """
        Resolve the locale and timezone for the incoming request and delegate downstream.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Discard any value inherited from an earlier request.
        current_locale.set("")
        current_timezone.set(None)

        request = Request(scope, receive)

        # Locale resolution order:
        #   1. ``locale_resolver`` (if it returns a non-None locale).
        #   2. ``Accept-Language`` header negotiated against supported locales.
        #   3. ``default_locale``.
        resolved_locale: str | None = None
        if self.locale_resolver is not None:
            resolved_locale = await _maybe_await(self.locale_resolver(request))
        if resolved_locale is None:
            accept_language = request.headers.get("accept-language", "")
            resolved_locale = negotiate_locale(
                accept_language,
                self.manager.supported_locales(),
                self.default_locale,
            )
        set_current_locale(resolved_locale)

        # Timezone resolution: a non-None return value from the resolver wins;
        # the default timezone (set at construction time) is otherwise left in
        # place via ``get_current_timezone`` falling back to it.
        if self.timezone_resolver is not None:
            resolved_timezone = await _maybe_await(self.timezone_resolver(request))
            if resolved_timezone is not None:
                set_current_timezone(resolve_timezone(resolved_timezone))

        await self.app(scope, receive, send)
