"""
Timezone context management.

Holds the current timezone in a :class:`contextvars.ContextVar` so it is safe
to use across async requests, background tasks, and threads. The resolved
timezone is used by the date/time helpers to format datetimes and times
against a user- or request-specific zone instead of the process local zone.

The active value is a :class:`datetime.tzinfo` (typically a
:class:`zoneinfo.ZoneInfo`). Callers may pass either an instance or an IANA
name (``"Europe/Madrid"``); the latter is normalized through
:func:`resolve_timezone` so that ``"UTC"``, ``"Z"`` and friends all yield a
usable ``tzinfo`` object.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import tzinfo
from zoneinfo import ZoneInfo

# Context variable holding the current timezone. ``None`` means "not yet
# resolved" and callers fall back to the process-wide default.
current_timezone: ContextVar[tzinfo | None] = ContextVar("current_timezone", default=None)

# Module-level default timezone, used when nothing else resolved one.
# It is configured by the middleware or manually in CLI scripts. ``None``
# means "no override" and the date/time helpers fall back to Babel's
# default (the process local zone).
_default_timezone: tzinfo | None = None  # pylint: disable=invalid-name


def resolve_timezone(value: tzinfo | str | None) -> tzinfo | None:
    """
    Normalize a timezone specification into a :class:`tzinfo` instance.

    Accepts a ``tzinfo`` subclass instance (returned as-is), an IANA name
    (``"Europe/Madrid"``, ``"UTC"``) or ``None`` (returned as-is). Strings
    are parsed with :class:`zoneinfo.ZoneInfo`; invalid names raise
    :class:`zoneinfo.ZoneInfoNotFoundError`.

    Args:
        value: A ``tzinfo`` instance, an IANA timezone name, or ``None``.
    """
    if value is None or isinstance(value, tzinfo):
        return value
    return ZoneInfo(value)


def set_default_timezone(timezone: tzinfo | str | None) -> None:
    """
    Set the process-wide default timezone.

    This is the value returned by :func:`get_current_timezone` when no
    timezone has been set for the current context. The FastAPI middleware
    sets this from its ``default_timezone`` argument; CLI scripts can call
    it directly. ``None`` disables the override and falls back to the
    process local zone.
    """
    global _default_timezone  # noqa: PLW0603  # pylint: disable=global-statement
    _default_timezone = resolve_timezone(timezone)


def get_default_timezone() -> tzinfo | None:
    """
    Return the process-wide default timezone, or ``None`` if none is set.
    """
    return _default_timezone


def set_current_timezone(timezone: tzinfo | str | None) -> Token[tzinfo | None]:
    """
    Force the timezone for the current context.

    Useful from user middleware (for example to honor a per-user preference)
    or from CLI scripts. Returns the :class:`~contextvars.Token` that can be
    passed to :func:`reset_current_timezone` to restore the previous value.
    """
    return current_timezone.set(resolve_timezone(timezone))


def reset_current_timezone(token: Token[tzinfo | None]) -> None:
    """
    Restore the timezone to the value captured before :func:`set_current_timezone`.
    """
    current_timezone.reset(token)


@contextmanager
def as_timezone(timezone: tzinfo | str | None) -> Iterator[tzinfo | None]:
    """
    Temporarily force the timezone for the duration of a ``with`` block.

    Sets the current timezone on entry and restores the previous value on
    exit, even if the block raises. This is the convenient wrapper around
    :func:`set_current_timezone` / :func:`reset_current_timezone`.

    Example:
        ::

            from fastapi_simple_i18n.timezone import as_timezone
            from fastapi_simple_i18n.helpers import t_datetime

            with as_timezone("Europe/Madrid"):
                when = t_datetime(some_datetime)

    Args:
        timezone: A ``tzinfo`` instance, an IANA name, or ``None`` to clear
            the override for the block.

    Yields:
        The resolved ``tzinfo`` (so ``with as_timezone("UTC") as tz:`` works
        too), or ``None`` if the override was cleared.
    """
    token = set_current_timezone(timezone)
    try:
        yield resolve_timezone(timezone)
    finally:
        reset_current_timezone(token)


def get_current_timezone() -> tzinfo | None:
    """
    Return the effective timezone for the current context.

    Resolution order:

    1. The timezone set with :func:`set_current_timezone` (or by the
       middleware).
    2. The process-wide default timezone (see :func:`set_default_timezone`).
    3. ``None``, which lets the date/time helpers use Babel's default (the
       process local zone).
    """
    timezone = current_timezone.get()
    if timezone is not None:
        return timezone
    return _default_timezone
