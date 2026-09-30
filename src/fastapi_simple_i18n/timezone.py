"""
Timezone resolution and timezone context management.

This module owns two things:

* :func:`resolve_timezone`, the single entry point that turns a timezone written
  anywhere (a query parameter, a resolver, a CLI argument) into a validated
  :class:`~datetime.tzinfo`.
* The per-context timezone, held in a :class:`contextvars.ContextVar` so it is
  safe across async requests, background tasks, and threads.

The timezone is never "absent". The process-wide default starts at
:data:`DEFAULT_TIMEZONE` (``UTC``) and is always a :class:`~datetime.tzinfo`,
and :func:`get_current_timezone` always answers with one. That is the whole
point of a timezone in a translation library: a moment rendered without a zone
is a moment whose wall clock depends on where the process happens to run, so
"the server's local time" is not a default worth having. Every function that
*takes* a timezone therefore rejects ``None``, the same way every function that
takes a locale rejects a tag that is not one.

The only ``None`` in the module is the one inside the
:class:`~contextvars.ContextVar`, where it means "nothing was resolved for this
context"; it is what makes :func:`reset_current_timezone` and the per-request
reset work, and it is never visible through the public getters.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import tzinfo
from zoneinfo import ZoneInfo

# The timezone in effect when nothing has been configured: UTC. It is resolved
# through :func:`resolve_timezone`, so it is the very object a caller passing
# ``"UTC"`` gets back, and the two are indistinguishable downstream.
DEFAULT_TIMEZONE: tzinfo = ZoneInfo("UTC")

# Context variable holding the current timezone. ``None`` means "not resolved in
# this context" and callers fall back to the process-wide default; it is never
# what a caller reads.
current_timezone: ContextVar[tzinfo | None] = ContextVar("current_timezone", default=None)

# Module-level default timezone, used when nothing else resolved one.
# It is configured by the middleware or manually in CLI scripts.
_default_timezone: tzinfo = DEFAULT_TIMEZONE  # pylint: disable=invalid-name


def resolve_timezone(timezone: tzinfo | str) -> tzinfo:
    """
    Turn anything that names a timezone into a validated :class:`tzinfo`.

    A ``tzinfo`` instance is returned as-is, and an IANA name
    (``"Europe/Madrid"``, ``"UTC"``) is parsed into a
    :class:`zoneinfo.ZoneInfo`.

    ``None`` is refused. There is always a timezone in effect, so a ``None``
    here could only mean "give me a different answer depending on which helper
    you asked", which is exactly the ambiguity this module removes.

    Args:
        timezone: A ``tzinfo`` instance or an IANA timezone name.

    Returns:
        The validated timezone.

    Raises:
        TypeError: If ``timezone`` is not a ``tzinfo`` or a string.
        ValueError: If ``timezone`` is an empty or blank string.
        ZoneInfoNotFoundError: If the name is not in the IANA database.
    """
    if isinstance(timezone, tzinfo):
        return timezone
    if not isinstance(timezone, str):
        raise TypeError(f"Invalid timezone {timezone!r}: expected a timezone string, got {type(timezone).__name__}")
    name = timezone.strip()
    if not name:
        raise ValueError("Invalid timezone: the value is empty")
    return ZoneInfo(name)


def set_default_timezone(timezone: tzinfo | str) -> None:
    """
    Set the process-wide default timezone.

    This is the value returned by :func:`get_current_timezone` when no
    timezone has been set for the current context. The FastAPI middleware sets
    this from its ``default_timezone`` argument; CLI scripts can call it
    directly. It starts at :data:`DEFAULT_TIMEZONE` and can never be unset, so
    ``get_current_timezone()`` always has something to answer with.

    Args:
        timezone: The timezone to use when no context resolved one.

    Raises:
        TypeError: If ``timezone`` is neither a ``tzinfo`` nor a string.
        ValueError: If ``timezone`` is an empty or blank string.
        ZoneInfoNotFoundError: If the name is not in the IANA database.
    """
    global _default_timezone  # noqa: PLW0603  # pylint: disable=global-statement
    _default_timezone = resolve_timezone(timezone)


def get_default_timezone() -> tzinfo:
    """
    Return the process-wide default timezone.

    Never ``None``: it is :data:`DEFAULT_TIMEZONE` until
    :func:`set_default_timezone` replaces it.
    """
    return _default_timezone


def set_current_timezone(timezone: tzinfo | str) -> Token[tzinfo | None]:
    """
    Force the timezone for the current context.

    Useful from user middleware (for example to honor a per-user preference)
    or from CLI scripts. Returns the :class:`~contextvars.Token` that can be
    passed to :func:`reset_current_timezone` to restore the previous value.

    Args:
        timezone: The timezone to activate.

    Returns:
        The token to hand to :func:`reset_current_timezone`.

    Raises:
        TypeError: If ``timezone`` is neither a ``tzinfo`` nor a string.
        ValueError: If ``timezone`` is an empty or blank string.
        ZoneInfoNotFoundError: If the name is not in the IANA database.
    """
    return current_timezone.set(resolve_timezone(timezone))


def reset_current_timezone(token: Token[tzinfo | None]) -> None:
    """
    Restore the timezone to the value captured before :func:`set_current_timezone`.
    """
    current_timezone.reset(token)


@contextmanager
def as_timezone(timezone: tzinfo | str) -> Iterator[tzinfo]:
    """
    Temporarily force the timezone for the duration of a ``with`` block.

    Sets the current timezone on entry and restores the previous value on exit,
    even if the block raises. This is the convenient wrapper around
    :func:`set_current_timezone` / :func:`reset_current_timezone`.

    Example:
        ::

            from fastapi_simple_i18n.timezone import as_timezone
            from fastapi_simple_i18n.helpers import t_datetime

            with as_timezone("Europe/Madrid"):
                when = t_datetime(some_datetime)

    Args:
        timezone: A ``tzinfo`` instance or an IANA name. ``None`` is refused,
            so a block always renders in a real zone.

    Yields:
        The activated :class:`~datetime.tzinfo` (so
        ``with as_timezone("UTC") as tz:`` works too).

    Raises:
        TypeError: If ``timezone`` is neither a ``tzinfo`` nor a string.
        ValueError: If ``timezone`` is an empty or blank string.
        ZoneInfoNotFoundError: If the name is not in the IANA database.
    """
    active = resolve_timezone(timezone)
    token = set_current_timezone(active)
    try:
        yield active
    finally:
        reset_current_timezone(token)


def get_current_timezone() -> tzinfo:
    """
    Return the effective timezone for the current context.

    Resolution order:

    1. The timezone set with :func:`set_current_timezone` (or by the
       middleware).
    2. The process-wide default timezone (see :func:`set_default_timezone`),
       which is :data:`DEFAULT_TIMEZONE` until it is changed.

    The result is never ``None``, so a caller can project a datetime onto it
    without first checking whether there is anything to project onto. To
    deliberately render in a specific zone for one call, pass ``tz=`` to
    :func:`~fastapi_simple_i18n.helpers.t_datetime` or
    :func:`~fastapi_simple_i18n.helpers.t_time` instead of mutating the
    context.
    """
    timezone = current_timezone.get()
    if timezone is not None:
        return timezone
    return _default_timezone
