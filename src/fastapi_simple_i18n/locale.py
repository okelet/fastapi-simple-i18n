"""
Locale resolution and locale context management.

This module owns two things:

* :func:`resolve_locale`, the single entry point that turns a locale written
  anywhere (a query parameter, an ``Accept-Language`` header, a JSON file name,
  a CLI argument) into a validated :class:`babel.core.Locale`.
* The per-context locale, held in a :class:`contextvars.ContextVar` so it is
  safe across async requests, background tasks, and threads.

Locales are stored as :class:`~babel.core.Locale` objects from the very first
moment they enter the library, and every function that *sets* one — the
process-wide default, the current one, and the built-in one of the
:class:`~fastapi_simple_i18n.manager.TranslationManager` — validates the value
it is given. A malformed or unusable locale therefore fails where it is
passed, with an actionable message, instead of surfacing much later as a
missing translation or a formatting error.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

from babel.core import Locale, UnknownLocaleError

# The separators a locale tag may be written with. Babel's
# :meth:`babel.core.Locale.parse` takes one separator at a time, and the two
# spellings are both in common use: ``en_US`` in file names, Babel calls and
# identifiers, ``en-US`` in ``Accept-Language`` headers and BCP 47. Mixing them
# in one tag is refused rather than guessed at.
LOCALE_SEPARATORS = ("_", "-")

# Context variable holding the current locale. ``None`` means "not yet
# resolved" and callers fall back to the process-wide default.
current_locale: ContextVar[Locale | None] = ContextVar("current_locale", default=None)

# Module-level default locale, used when nothing else resolved a locale.
# It is configured by the middleware or manually in CLI scripts.
_default_locale: Locale = Locale.parse("en")  # pylint: disable=invalid-name


def resolve_locale(locale: str | Locale) -> Locale:
    """
    Turn anything that names a locale into a validated :class:`Locale`.

    Every spelling in use is accepted, and normalized to the single form Babel
    builds its identifiers from:

    * both separators (``es``, ``es_ES``, ``es-ES``), but only one at a time;
    * simple (``es``) and composite tags (``es_ES``, ``zh_Hans_CN``,
      ``en_US_POSIX``);
    * any casing (``ES-es``, ``ZH-hans-cn``).

    Normalization is what makes the rest of the library predictable: a
    translation registered as ``"pt-BR"`` is found again through ``"pt_BR"``,
    and a locale read from an ``Accept-Language`` header equals one read from
    a file name. A :class:`~babel.core.Locale` passed in is returned as-is.

    Args:
        locale: The locale to resolve, as a tag or an existing
            :class:`~babel.core.Locale`.

    Returns:
        The validated, normalized locale.

    Raises:
        ValueError: If the tag is empty, mixes both separators, is malformed
            (``english``, ``en--US``), or names a locale CLDR does not know
            (``xx_YY``). The message says which of the two it was.
    """
    if isinstance(locale, Locale):
        return locale
    if not isinstance(locale, str):
        raise ValueError(f"Invalid locale {locale!r}: expected a locale string, got {type(locale).__name__}")

    text = locale.strip()
    if not text:
        raise ValueError("Invalid locale: the value is empty")

    separators = [separator for separator in LOCALE_SEPARATORS if separator in text]
    if len(separators) > 1:
        raise ValueError(f"Invalid locale {locale!r}: use a single separator, '_' or '-', not both")

    try:
        return Locale.parse(text, sep=separators[0] if separators else "_")
    except (UnknownLocaleError, ValueError) as exc:
        raise ValueError(f"Invalid locale {locale!r}: {exc}") from exc


def set_default_locale(locale: str | Locale) -> None:
    """
    Set the process-wide default locale.

    This is the value returned by :func:`get_current_locale` when no locale has
    been set for the current context. The FastAPI middleware sets this from its
    ``default_locale`` argument; CLI scripts can call it directly.

    Args:
        locale: The locale to use when no context resolved one.

    Raises:
        ValueError: If ``locale`` is not a valid locale tag.
    """
    global _default_locale  # noqa: PLW0603  # pylint: disable=global-statement
    _default_locale = resolve_locale(locale)


def get_default_locale() -> Locale:
    """
    Return the process-wide default locale.
    """
    return _default_locale


def set_current_locale(locale: str | Locale) -> Token[Locale | None]:
    """
    Force the locale for the current context.

    Useful from user middleware (for example to honor a per-user preference) or
    from CLI scripts. Returns the :class:`~contextvars.Token` that can be passed
    to :func:`reset_current_locale` to restore the previous value.

    Args:
        locale: The locale to activate.

    Returns:
        The token to hand to :func:`reset_current_locale`.

    Raises:
        ValueError: If ``locale`` is not a valid locale tag.
    """
    return current_locale.set(resolve_locale(locale))


def reset_current_locale(token: Token[Locale | None]) -> None:
    """
    Restore the locale to the value captured before :func:`set_current_locale`.
    """
    current_locale.reset(token)


@contextmanager
def as_locale(locale: str | Locale) -> Iterator[Locale]:
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
                message = t("Hello, {name}!", name="Ada")

    Args:
        locale: The locale to activate inside the block.

    Yields:
        The activated :class:`~babel.core.Locale` (so
        ``with as_locale("es") as loc:`` works too).

    Raises:
        ValueError: If ``locale`` is not a valid locale tag.
    """
    active = resolve_locale(locale)
    token = set_current_locale(active)
    try:
        yield active
    finally:
        reset_current_locale(token)


def get_current_locale() -> Locale:
    """
    Return the effective locale for the current context.

    Resolution order:

    1. The locale set with :func:`set_current_locale` (or by the middleware).
    2. The process-wide default locale (see :func:`set_default_locale`).

    The result is never ``None``: one of the two above always applies, and both
    are stored as a validated :class:`~babel.core.Locale`.

    Use ``str(...)`` on the result wherever a plain string is required (a JSON
    payload, a file name); ``locale.language`` and ``locale.territory`` are
    available when a subtag is what you actually want.
    """
    locale = current_locale.get()
    if locale is not None:
        return locale
    return _default_locale
