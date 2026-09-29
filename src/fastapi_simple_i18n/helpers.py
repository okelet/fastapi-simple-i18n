"""
Translation and formatting helpers.

Two flavours of every helper, two contracts:

* The eager form (``t`` / ``t_number`` / ``t_date`` / ``t_time`` / ``t_datetime``)
  resolves against the locale active at call time and returns a real
  ``str`` (or, for the formatters, a ``str`` with the formatted text).
  The result is plain text wherever a string is expected: ``json.dumps``,
  ``urllib.parse.quote``, Pydantic str fields, ``| tojson`` in Jinja,
  concatenation, f-strings. No ``str(...)`` wrapper is needed at call
  sites.
* The lazy form (``lazy_t`` / ``lazy_t_number`` / ``lazy_t_date`` /
  ``lazy_t_time`` / ``lazy_t_datetime``) defers the lookup until the
  value is rendered. It reads the locale active then, so a message
  captured at module import time will render in whichever locale is
  active when something actually reads it. The lazy objects are
  *not* ``str`` subclasses — they are string-like wrappers that resolve
  in every relevant dunder (``__str__``, ``__format__``, ``__add__``,
  ``__radd__``, ``__mod__``, ``__eq__``, ``__hash__``, ``__contains__``,
  ``__len__``, ``__getitem__``, ``__iter__``). Wrap them with ``str()``
  at any boundary that needs a real string (``json.dumps``,
  ``urllib.parse.quote``, ``| tojson``, Pydantic str fields).
"""

import logging
from collections.abc import Callable
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from babel.dates import format_date, format_datetime, format_time
from babel.numbers import format_decimal

from .locale import get_current_locale
from .registry import get_translation_manager

logger = logging.getLogger(__name__)


# --- Eager: t() returns a str subclass carrying the translated text ---


class TranslatableStr(str):
    """
    A ``str`` carrying a translated message.

    The lookup happens against the locale active at construction time, so
    the value is final: the object behaves like any other ``str`` and works
    everywhere a string is expected.

    Defined as a subclass (and not aliased to ``str``) so introspection and
    tests can still tell translated strings apart when needed.
    """

    __slots__ = ("key", "variant", "params")

    def __new__(cls, key: str, variant: str | None = None, **params: Any) -> TranslatableStr:
        """
        Resolve the translation against the active locale and return a real str.

        Args:
            key: The source string to translate.
            variant: Optional variant to disambiguate identical keys.
            **params: Named parameters applied with :meth:`str.format`.
        """
        target_locale = get_current_locale()
        manager = get_translation_manager()
        translated = manager.translate(key, variant=variant, locale=target_locale)
        if params:
            try:
                translated = translated.format(**params)
            except KeyError, IndexError, ValueError:
                logger.warning("Failed to format translation %r with %r", translated, params)
        instance = super().__new__(cls, translated)
        instance.key = key
        instance.variant = variant
        instance.params = params
        return instance


def t(key: str, _variant: str | None = None, **params: Any) -> TranslatableStr:
    """
    Translate a source string eagerly, returning a real ``str``.

    The lookup uses the locale active at call time, so the value is final
    and works anywhere a string is expected (``json.dumps``, Pydantic
    fields, ``urllib.parse.quote``, concatenation, f-strings, ``| tojson``
    in Jinja) with no ``str(...)`` wrapper.

    Use :func:`lazy_t` when the value must track a locale that may change
    later (a module-level constant, a decorator that runs before the
    request, a pre-built message rendered from a different context).

    Examples:
        ::

            t("Yes")
            t("Archive", _variant="noun")
            t("There are {n} items", n=item_count)

    Args:
        key: The source string to translate.
        _variant: Optional variant (leading underscore avoids clashing with
            a ``variant`` format parameter).
        **params: Named parameters applied with :meth:`str.format`.
    """
    return TranslatableStr(key, variant=_variant, **params)


def t_number(value: int | float | Decimal, format: str = "#,##0.###", locale: str | None = None) -> str:  # noqa: A002  # pylint: disable=redefined-builtin
    """
    Format a number eagerly, returning a real ``str``.

    Uses the locale active at call time; pass ``locale`` explicitly to
    override. ``format`` is a Babel pattern (the default ``"#,##0.###"``)
    or one of the named styles.
    """
    return format_decimal(value, format=format, locale=locale or get_current_locale())


def t_date(value: date | datetime, format: str = "medium", locale: str | None = None) -> str:  # noqa: A002  # pylint: disable=redefined-builtin
    """
    Format a date eagerly, returning a real ``str``.

    ``format`` is ``"short"``, ``"medium"``, ``"long"``, ``"full"``, or a
    Babel pattern.
    """
    return format_date(value, format=format, locale=locale or get_current_locale())


def t_time(value: time | datetime, format: str = "short", locale: str | None = None) -> str:  # noqa: A002  # pylint: disable=redefined-builtin
    """
    Format a time eagerly, returning a real ``str``.
    """
    return format_time(value, format=format, locale=locale or get_current_locale())


def t_datetime(value: datetime, format: str = "medium", locale: str | None = None) -> str:  # noqa: A002  # pylint: disable=redefined-builtin
    """
    Format a datetime eagerly, returning a real ``str``.
    """
    return format_datetime(value, format=format, locale=locale or get_current_locale())


# --- Lazy helpers ------------------------------------------------------
#
# Lazy helpers return string-like objects that defer the locale lookup
# (and, for the formatters, the formatting itself) until the value is
# read. They are NOT str subclasses — they implement the relevant dunders
# so they behave like strings in user code, but anything that goes
# through the C-level str protocol (json.dumps, encode, Pydantic str
# fields) needs an explicit str() wrapper at the boundary.
#
# The implementation is small and uniform: every lazy object stores a
# single ``_resolve`` callable that returns a fresh str on demand. All
# the dunders go through that callable.


class LazyTranslatableStr:
    """
    A string-like object that defers translation until rendered.

    Resolves against the locale active when the value is read (in
    ``__str__``, ``__format__``, ``__add__``, etc.). NOT a ``str``
    subclass — operations that bypass Python's dunder protocol
    (``json.dumps``, ``str.encode``, Pydantic str fields, ``| tojson``)
    need an explicit ``str(...)`` wrapper at the boundary.
    """

    __slots__ = ("_resolve",)

    def __init__(self, resolve: Callable[[], str]) -> None:
        """
        Capture the callable that produces the translated string.

        Args:
            resolve: Callable that returns the translated string. Called
                each time the value is read; the active locale at that
                moment is what determines the result.
        """
        self._resolve = resolve

    def resolve(self) -> str:
        """Resolve the translation against the active locale."""
        return self._resolve()

    # --- str protocol ---

    def __str__(self) -> str:
        return self._resolve()

    def __repr__(self) -> str:
        return f"lazy_t({self._resolve()!r})"

    def __format__(self, format_spec: str) -> str:
        return format(self._resolve(), format_spec)

    def __bool__(self) -> bool:
        return bool(self._resolve())

    # --- String operations ---

    def __add__(self, other: object) -> str:
        return self._resolve() + other  # type: ignore[operator]

    def __radd__(self, other: object) -> str:
        return other + self._resolve()  # type: ignore[operator]

    def __mul__(self, n: int) -> str:
        return self._resolve() * n

    def __rmul__(self, n: int) -> str:
        return n * self._resolve()

    def __mod__(self, args: Any) -> str:
        return self._resolve() % args

    def __rmod__(self, template: Any) -> str:
        return template % self._resolve()

    # --- Comparison / hash / membership / sequence ---

    def __eq__(self, other: object) -> bool:
        if isinstance(other, LazyTranslatableStr):
            return self._resolve() == other._resolve()
        if isinstance(other, str):
            return self._resolve() == other
        return NotImplemented

    def __ne__(self, other: object) -> bool:
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __lt__(self, other: object) -> bool:
        return self._resolve() < other  # type: ignore[operator]

    def __le__(self, other: object) -> bool:
        return self._resolve() <= other  # type: ignore[operator]

    def __gt__(self, other: object) -> bool:
        return self._resolve() > other  # type: ignore[operator]

    def __ge__(self, other: object) -> bool:
        return self._resolve() >= other  # type: ignore[operator]

    def __hash__(self) -> int:
        return hash(self._resolve())

    def __contains__(self, item: object) -> bool:
        return item in self._resolve()

    def __len__(self) -> int:
        return len(self._resolve())

    def __getitem__(self, index: Any) -> str:
        return self._resolve()[index]

    def __iter__(self):
        return iter(self._resolve())


def lazy_t(key: str, _variant: str | None = None, **params: Any) -> LazyTranslatableStr:
    """
    Translate a source string lazily, deferring the lookup until render.

    The returned object resolves to the translated string when converted
    with ``str()``, interpolated with ``%``, concatenated, compared or
    otherwise read. It reads the locale active at render time, not at
    call time.

    Use this when the value is captured at a point where the locale is
    not yet known (a module-level constant, a decorator that runs before
    the request, etc.) and must track whichever locale is active later.

    Not a ``str`` subclass. Wrap with ``str(...)`` at boundaries that
    expect a real string (``json.dumps``, ``urllib.parse.quote``, Pydantic
    str fields, ``| tojson`` in Jinja).

    Args:
        key: The source string to translate.
        _variant: Optional variant.
        **params: Named parameters applied with :meth:`str.format`.
    """

    def _resolve() -> str:
        target_locale = get_current_locale()
        manager = get_translation_manager()
        translated = manager.translate(key, variant=_variant, locale=target_locale)
        if params:
            try:
                translated = translated.format(**params)
            except KeyError, IndexError, ValueError:
                logger.warning("Failed to format lazy translation %r with %r", translated, params)
        return translated

    return LazyTranslatableStr(_resolve)


# --- Lazy formatters ----------------------------------------------------
#
# Same pattern as LazyTranslatableStr: a callable that returns a formatted
# string on demand. The formatter stores the value, the format spec and
# an optional explicit locale override; the current locale is read on
# each resolve call. ``format`` (``"medium"``, ``"short"``, etc.) is a
# value known at call time and is passed through to Babel.


class LazyNumber:
    """
    A string-like wrapper that defers number formatting until rendered.

    The locale is read when ``__str__`` (or any other string operation) is
    called, so a value captured with one locale will re-render in
    whatever locale is active later.
    """

    __slots__ = ("_value", "_format", "_locale")

    def __init__(self, value: int | float | Decimal, *, format: str = "#,##0.###", locale: str | None = None) -> None:  # noqa: A002  # pylint: disable=redefined-builtin
        """
        Capture the value, format spec and optional explicit locale override.

        Args:
            value: The number to format.
            format: Babel pattern (default ``"#,##0.###"``) or a named style.
            locale: Optional locale override; defaults to the active locale
                at resolve time.
        """
        self._value = value
        self._format = format
        self._locale = locale

    def resolve(self) -> str:
        """
        Format the number against the active locale.
        """
        return format_decimal(self._value, format=self._format, locale=self._locale or get_current_locale())

    def __str__(self) -> str:
        return self.resolve()

    def __repr__(self) -> str:
        return f"lazy_t_number({self._value!r})"

    def __format__(self, format_spec: str) -> str:
        return format(self.resolve(), format_spec)

    def __bool__(self) -> bool:
        return bool(self.resolve())

    def __add__(self, other: object) -> str:
        return self.resolve() + other  # type: ignore[operator]

    def __radd__(self, other: object) -> str:
        return other + self.resolve()  # type: ignore[operator]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, LazyNumber):
            return self.resolve() == other.resolve()
        return self.resolve() == other

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return hash(self.resolve())

    def __contains__(self, item: object) -> bool:
        return item in self.resolve()

    def __len__(self) -> int:
        return len(self.resolve())


class LazyDate:
    """A string-like wrapper that defers date formatting until rendered."""

    __slots__ = ("_value", "_format", "_locale")

    def __init__(self, value: date | datetime, *, format: str = "medium", locale: str | None = None) -> None:  # noqa: A002  # pylint: disable=redefined-builtin
        """
        Capture the value, format spec and optional explicit locale override.

        Args:
            value: The date (or datetime) to format.
            format: ``"short"``, ``"medium"``, ``"long"``, ``"full"`` or a
                Babel pattern.
            locale: Optional locale override; defaults to the active locale
                at resolve time.
        """
        self._value = value
        self._format = format
        self._locale = locale

    def resolve(self) -> str:
        """
        Format the date against the active locale.
        """
        return format_date(self._value, format=self._format, locale=self._locale or get_current_locale())

    def __str__(self) -> str:
        return self.resolve()

    def __repr__(self) -> str:
        return f"lazy_t_date({self._value!r})"

    def __format__(self, format_spec: str) -> str:
        return format(self.resolve(), format_spec)

    def __bool__(self) -> bool:
        return bool(self.resolve())

    def __add__(self, other: object) -> str:
        return self.resolve() + other  # type: ignore[operator]

    def __radd__(self, other: object) -> str:
        return other + self.resolve()  # type: ignore[operator]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, LazyDate):
            return self.resolve() == other.resolve()
        return self.resolve() == other

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return hash(self.resolve())

    def __contains__(self, item: object) -> bool:
        return item in self.resolve()

    def __len__(self) -> int:
        return len(self.resolve())


class LazyTime:
    """A string-like wrapper that defers time formatting until rendered."""

    __slots__ = ("_value", "_format", "_locale")

    def __init__(self, value: time | datetime, *, format: str = "short", locale: str | None = None) -> None:  # noqa: A002  # pylint: disable=redefined-builtin
        """
        Capture the value, format spec and optional explicit locale override.

        Args:
            value: The time (or datetime) to format.
            format: ``"short"``, ``"medium"``, ``"long"``, ``"full"`` or a
                Babel pattern.
            locale: Optional locale override; defaults to the active locale
                at resolve time.
        """
        self._value = value
        self._format = format
        self._locale = locale

    def resolve(self) -> str:
        """
        Format the time against the active locale.
        """
        return format_time(self._value, format=self._format, locale=self._locale or get_current_locale())

    def __str__(self) -> str:
        return self.resolve()

    def __repr__(self) -> str:
        return f"lazy_t_time({self._value!r})"

    def __format__(self, format_spec: str) -> str:
        return format(self.resolve(), format_spec)

    def __bool__(self) -> bool:
        return bool(self.resolve())

    def __add__(self, other: object) -> str:
        return self.resolve() + other  # type: ignore[operator]

    def __radd__(self, other: object) -> str:
        return other + self.resolve()  # type: ignore[operator]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, LazyTime):
            return self.resolve() == other.resolve()
        return self.resolve() == other

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return hash(self.resolve())

    def __contains__(self, item: object) -> bool:
        return item in self.resolve()

    def __len__(self) -> int:
        return len(self.resolve())


class LazyDateTime:
    """A string-like wrapper that defers datetime formatting until rendered."""

    __slots__ = ("_value", "_format", "_locale")

    def __init__(self, value: datetime, *, format: str = "medium", locale: str | None = None) -> None:  # noqa: A002  # pylint: disable=redefined-builtin
        """
        Capture the value, format spec and optional explicit locale override.

        Args:
            value: The datetime to format.
            format: ``"short"``, ``"medium"``, ``"long"``, ``"full"`` or a
                Babel pattern.
            locale: Optional locale override; defaults to the active locale
                at resolve time.
        """
        self._value = value
        self._format = format
        self._locale = locale

    def resolve(self) -> str:
        """
        Format the datetime against the active locale.
        """
        return format_datetime(self._value, format=self._format, locale=self._locale or get_current_locale())

    def __str__(self) -> str:
        return self.resolve()

    def __repr__(self) -> str:
        return f"lazy_t_datetime({self._value!r})"

    def __format__(self, format_spec: str) -> str:
        return format(self.resolve(), format_spec)

    def __bool__(self) -> bool:
        return bool(self.resolve())

    def __add__(self, other: object) -> str:
        return self.resolve() + other  # type: ignore[operator]

    def __radd__(self, other: object) -> str:
        return other + self.resolve()  # type: ignore[operator]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, LazyDateTime):
            return self.resolve() == other.resolve()
        return self.resolve() == other

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return hash(self.resolve())

    def __contains__(self, item: object) -> bool:
        return item in self.resolve()

    def __len__(self) -> int:
        return len(self.resolve())


def lazy_t_number(value: int | float | Decimal, format: str = "#,##0.###", locale: str | None = None) -> LazyNumber:  # noqa: A002  # pylint: disable=redefined-builtin
    """
    Format a number lazily.

    Returns a string-like wrapper that formats the value against the
    locale active when the value is read.
    """
    return LazyNumber(value, format=format, locale=locale)


def lazy_t_date(value: date | datetime, format: str = "medium", locale: str | None = None) -> LazyDate:  # noqa: A002  # pylint: disable=redefined-builtin
    """
    Format a date lazily.

    Returns a string-like wrapper that formats the value against the
    locale active when the value is read.
    """
    return LazyDate(value, format=format, locale=locale)


def lazy_t_time(value: time | datetime, format: str = "short", locale: str | None = None) -> LazyTime:  # noqa: A002  # pylint: disable=redefined-builtin
    """
    Format a time lazily.

    Returns a string-like wrapper that formats the value against the
    locale active when the value is read.
    """
    return LazyTime(value, format=format, locale=locale)


def lazy_t_datetime(value: datetime, format: str = "medium", locale: str | None = None) -> LazyDateTime:  # noqa: A002  # pylint: disable=redefined-builtin
    """
    Format a datetime lazily.

    Returns a string-like wrapper that formats the value against the
    locale active when the value is read.
    """
    return LazyDateTime(value, format=format, locale=locale)
