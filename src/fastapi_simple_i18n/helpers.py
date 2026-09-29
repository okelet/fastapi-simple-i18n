"""
Translation and formatting helpers.

Provides :func:`t` (and its formatting siblings) which return lazy translation
objects. A :class:`LazyTranslation` resolves to a string only when it is
rendered (via ``str()``), so the value reflects the locale that is active at
render time rather than at call time. This is what makes module-level and
template-level translations behave correctly.
"""

import logging
from datetime import date, datetime, time
from decimal import Decimal

from babel.dates import format_date, format_datetime, format_time
from babel.numbers import format_decimal

from .locale import get_current_locale
from .registry import get_translation_manager

logger = logging.getLogger(__name__)


class LazyTranslation:
    """
    A deferred translation resolved when converted to a string.

    The key, variant, and format parameters are captured at creation time; the
    locale and the actual lookup happen in :meth:`__str__`. This lets you store
    a translation as a module-level constant or pass it around before a locale
    is known.
    """

    __slots__ = ("key", "variant", "params")

    def __init__(self, key: str, variant: str | None = None, **params: object) -> None:
        """
        Capture the translation request.

        Args:
            key: The source string to translate.
            variant: Optional variant to disambiguate identical keys.
            **params: Named parameters applied with :meth:`str.format`.
        """
        self.key = key
        self.variant = variant
        self.params = params

    def resolve(self, locale: str | None = None) -> str:
        """
        Resolve the translation to a concrete string.

        Args:
            locale: Locale to resolve against. Defaults to the current locale.
        """
        target_locale = locale or get_current_locale()
        manager = get_translation_manager()
        translated = manager.translate(self.key, variant=self.variant, locale=target_locale)
        if self.params:
            try:
                return translated.format(**self.params)
            except (KeyError, IndexError, ValueError):
                logger.warning("Failed to format translation %r with %r", translated, self.params)
        return translated

    def __str__(self) -> str:
        """
        Resolve the translation using the current locale.
        """
        return self.resolve()

    def __repr__(self) -> str:
        """
        Return a debug representation.
        """
        return f"LazyTranslation(key={self.key!r}, variant={self.variant!r}, params={self.params!r})"

    def __eq__(self, other: object) -> bool:
        """
        Compare against the resolved string or another lazy translation.
        """
        if isinstance(other, LazyTranslation):
            return str(self) == str(other)
        if isinstance(other, str):
            return str(self) == other
        return NotImplemented

    def __hash__(self) -> int:
        """
        Hash based on the resolved string.
        """
        return hash(str(self))


def t(key: str, _variant: str | None = None, **params: object) -> LazyTranslation:
    """
    Translate a source string, returning a lazy translation.

    The returned object renders to the translated string when converted with
    ``str()``. Named parameters are applied with :meth:`str.format`.

    Examples:
        ::

            t("Yes")
            t("Archive", _variant="noun")
            t("There are {item_count} items", item_count=item_count)

    Args:
        key: The source string to translate.
        _variant: Optional variant (leading underscore avoids clashing with a
            ``variant`` format parameter).
        **params: Named parameters applied with :meth:`str.format`.
    """
    return LazyTranslation(key, variant=_variant, **params)


def t_number(value: int | float | Decimal, locale: str | None = None) -> str:
    """
    Format a number for the current (or given) locale.

    Examples:
        ``1234.5`` renders as ``"1,234.5"`` (en) or ``"1.234,5"`` (es).
    """
    return format_decimal(value, locale=locale or get_current_locale())


def t_date(value: date | datetime, format: str = "medium", locale: str | None = None) -> str:  # noqa: A002  # pylint: disable=redefined-builtin
    """
    Format a date for the current (or given) locale.

    Format options: ``"short"``, ``"medium"``, ``"long"``, ``"full"``, or a
    custom Babel pattern.
    """
    return format_date(value, format=format, locale=locale or get_current_locale())


def t_time(value: time | datetime, format: str = "short", locale: str | None = None) -> str:  # noqa: A002  # pylint: disable=redefined-builtin
    """
    Format a time for the current (or given) locale.

    Format options: ``"short"``, ``"medium"``, ``"long"``, ``"full"``, or a
    custom Babel pattern.
    """
    return format_time(value, format=format, locale=locale or get_current_locale())


def t_datetime(value: datetime, format: str = "medium", locale: str | None = None) -> str:  # noqa: A002  # pylint: disable=redefined-builtin
    """
    Format a datetime for the current (or given) locale.

    Format options: ``"short"``, ``"medium"``, ``"long"``, ``"full"``, or a
    custom Babel pattern.
    """
    return format_datetime(value, format=format, locale=locale or get_current_locale())
