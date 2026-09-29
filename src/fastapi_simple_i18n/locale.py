"""
Locale context management.

Holds the current locale in a :class:`contextvars.ContextVar` so it is safe to
use across async requests, background tasks, and threads. The resolved locale
is used by the translation helpers to pick the right ``Translation``.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

# Context variable holding the current locale (e.g. "es", "en").
# An empty string means "not yet resolved" and callers fall back to a default.
current_locale: ContextVar[str] = ContextVar("current_locale", default="")

# Module-level default locale, used when nothing else resolved a locale.
# It is configured by the middleware or manually in CLI scripts.
_default_locale: str = "en"  # pylint: disable=invalid-name


def set_default_locale(locale: str) -> None:
    """
    Set the process-wide default locale.

    This is the value returned by :func:`get_current_locale` when no locale has
    been set for the current context. The FastAPI middleware sets this from its
    ``default_locale`` argument; CLI scripts can call it directly.
    """
    global _default_locale  # noqa: PLW0603  # pylint: disable=global-statement
    _default_locale = locale


def get_default_locale() -> str:
    """
    Return the process-wide default locale.
    """
    return _default_locale


def set_current_locale(locale: str) -> Token[str]:
    """
    Force the locale for the current context.

    Useful from user middleware (for example to honor a per-user preference) or
    from CLI scripts. Returns the :class:`~contextvars.Token` that can be passed
    to :func:`reset_current_locale` to restore the previous value.
    """
    return current_locale.set(locale)


def reset_current_locale(token: Token[str]) -> None:
    """
    Restore the locale to the value captured before :func:`set_current_locale`.
    """
    current_locale.reset(token)


@contextmanager
def as_locale(locale: str) -> Iterator[str]:
    """
    Temporarily force the locale for the duration of a ``with`` block.

    Sets the current locale on entry and restores the previous value on exit,
    even if the block raises. This is the convenient wrapper around
    :func:`set_current_locale` / :func:`reset_current_locale`.

    Example:
        ::

            from fastapi_simple_i18n.locale import as_locale
            from fastapi_simple_i18n.helpers import t

            with as_locale("es"):
                message = str(t("Hello, {name}!", name="Ada"))

    Args:
        locale: The locale to activate inside the block.

    Yields:
        The locale that was activated (so ``with as_locale("es") as loc:``
        works too).
    """
    token = set_current_locale(locale)
    try:
        yield locale
    finally:
        reset_current_locale(token)


def get_current_locale() -> str:
    """
    Return the effective locale for the current context.

    Resolution order:

    1. The locale set with :func:`set_current_locale` (or by the middleware).
    2. The process-wide default locale (see :func:`set_default_locale`).
    """
    locale = current_locale.get()
    if locale:
        return locale
    return _default_locale
