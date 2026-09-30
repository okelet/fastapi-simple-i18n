"""
Translation and formatting helpers.

Two flavours of every helper, two contracts:

* The eager form (``t`` / ``t_number`` / ``t_money`` / ``t_amount`` /
  ``t_date`` / ``t_time`` / ``t_datetime``) resolves against the locale
  active at call time and returns a real ``str``. The result is plain text
  wherever a string is expected: ``json.dumps``, ``urllib.parse.quote``,
  Pydantic str fields, ``| tojson`` in Jinja, concatenation, f-strings.
  No ``str(...)`` wrapper is needed at call sites.
* The lazy form (``lazy_t`` / ``lazy_t_number`` / ``lazy_t_money`` /
  ``lazy_t_amount`` / ``lazy_t_date`` / ``lazy_t_time`` /
  ``lazy_t_datetime``) defers the lookup until the value is rendered. It
  reads the locale active then, so a message captured at module import
  time will render in whichever locale is active when something actually
  reads it. The lazy objects are *not* ``str`` subclasses — they are
  string-like wrappers that resolve in every relevant dunder (``__str__``,
  ``__format__``, ``__add__``, ``__radd__``, ``__mod__``, ``__eq__``,
  ``__hash__``, ``__contains__``, ``__len__``, ``__getitem__``,
  ``__iter__``). Wrap them with ``str()`` at any boundary that needs a
  real string (``json.dumps``, ``urllib.parse.quote``, ``| tojson``,
  Pydantic str fields).

Every helper that takes a ``locale`` argument accepts the same three
inputs — a locale tag, an already resolved
:class:`babel.core.Locale`, or ``None`` for "whichever locale is active
right now" — and validates a tag the moment it is passed, so a typo in
``t_date(..., locale="en-UK")`` fails at that call rather than deep inside
Babel's formatting.
"""

import logging
from collections.abc import Callable
from datetime import date, datetime, time, tzinfo
from decimal import Decimal
from typing import Any

from babel.dates import format_date, format_datetime, format_time
from babel.numbers import format_currency, format_decimal, list_currencies

from .locale import Locale, get_current_locale, resolve_locale
from .registry import get_translation_manager
from .timezone import get_current_timezone, resolve_timezone

logger = logging.getLogger(__name__)

# Pattern used by the money helpers. Two decimals always, so an amount reads
# like an amount rather than like a bare number.
MONEY_FORMAT = "#,##0.00"


def _resolve_tz(tz: tzinfo | str | None) -> tzinfo:
    """
    Pick the effective timezone for a single call.

    Explicit values (``tzinfo`` instance or IANA name) win over the context
    one. ``None`` means "whatever is active right now", which is itself always
    a concrete :class:`~datetime.tzinfo` (:data:`~fastapi_simple_i18n.timezone.DEFAULT_TIMEZONE`
    until something is configured), so the result is never ``None`` and a naive
    datetime is always projected onto a known zone.

    Note that ``None`` here means "use the active one", not "unset the
    timezone": a formatter has no way to express the latter, and there is no
    longer a value for it.
    """
    if tz is None:
        return get_current_timezone()
    return resolve_timezone(tz)


def _babel_locale(locale: str | Locale | None = None) -> Locale:
    """
    Return the locale to hand to Babel for a single call.

    An explicit ``locale`` overrides the active one and is validated the same
    way :func:`~fastapi_simple_i18n.locale.set_current_locale` validates its
    argument: any spelling of a locale tag is accepted (``"es"``, ``"es-ES"``,
    ``"es_ES"``, ``"ES-es"``) and normalized to the single
    :class:`~babel.core.Locale` Babel formats with. ``None`` means "use the
    locale active at call time", which the context API already stores as a
    validated locale, so the result is never a made-up fallback.

    Args:
        locale: The locale to use, or ``None`` for the active one.

    Returns:
        The resolved locale.

    Raises:
        ValueError: If ``locale`` is not a valid locale tag.
    """
    return get_current_locale() if locale is None else resolve_locale(locale)


def _format_money(value: int | float | Decimal, currency: str, locale: Locale) -> str:
    """
    Format a monetary amount, degrading instead of raising.

    Money reaches templates and CLI output, where a crash over a mistyped
    currency code is worse than a number without its symbol. So a blank or
    unrecognised ``currency`` renders as a plain localized decimal, after a
    warning naming the code. The locale itself needs no such fallback: it was
    validated before it got here, so Babel can always format with it.

    Args:
        value: The amount to format.
        currency: The ISO currency code (``"EUR"``, ``"usd"``); may be blank.
        locale: The resolved locale to format with.
    """
    code = currency.strip().upper()
    if not code:
        return format_decimal(value, format=MONEY_FORMAT, locale=locale)
    if code in list_currencies():
        return format_currency(value, code, locale=locale)
    logger.warning("Unknown currency code %r; rendering a plain decimal", currency)
    return format_decimal(value, format=MONEY_FORMAT, locale=locale)


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
            except (KeyError, IndexError, ValueError):
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


def t_number(value: int | float | Decimal, format: str = "#,##0.###", locale: str | Locale | None = None) -> str:  # noqa: A002  # pylint: disable=redefined-builtin
    """
    Format a number eagerly, returning a real ``str``.

    Uses the locale active at call time; pass ``locale`` explicitly to
    override. ``format`` is a Babel pattern (the default ``"#,##0.###"``)
    or one of the named styles.

    Args:
        value: The number to format.
        format: Babel pattern or named style.
        locale: Locale override, or ``None`` for the active one.

    Raises:
        ValueError: If ``locale`` is not a valid locale tag.
    """
    return format_decimal(value, format=format, locale=_babel_locale(locale))


# --- Currency / money helpers ------------------------------------------
#
# These wrappers sit on top of Babel's ``format_currency`` / ``format_decimal``
# so callers get the active locale for free, with a graceful fallback when a
# currency code is missing or unknown (we degrade to a plain localised decimal
# rather than crash). They round out the rest of the helpers for the common
# case of rendering monetary amounts in templates and CLI scripts.


def t_money(value: int | float | Decimal, currency: str = "", locale: str | Locale | None = None) -> str:  # noqa: A002  # pylint: disable=redefined-builtin
    """
    Format a monetary amount with its currency symbol in the active locale.

    Uses the locale active at call time; pass ``locale`` explicitly to
    override. ``currency`` is the ISO currency code (``"EUR"``, ``"USD"``;
    case-insensitive); when it is blank or Babel does not recognise it, the
    helper falls back to a plain localised decimal with two decimals
    (:data:`MONEY_FORMAT`), so a bad currency code never breaks rendering.

    Args:
        value: The amount to format.
        currency: ISO currency code, or ``""`` for no currency.
        locale: Locale override, or ``None`` for the active one.

    Raises:
        ValueError: If ``locale`` is not a valid locale tag.
    """
    return _format_money(value, currency, _babel_locale(locale))


def t_amount(value: int | float | Decimal, format: str = MONEY_FORMAT, locale: str | Locale | None = None) -> str:  # noqa: A002  # pylint: disable=redefined-builtin
    """
    Format a plain decimal amount (no currency symbol) in the active locale.

    Used for aggregate sums that may mix currencies, so no currency code is
    attached. ``format`` is a Babel pattern; the default
    (:data:`MONEY_FORMAT`) always shows two decimals so totals look like
    ``1,234.50`` / ``1.234,50`` instead of the generic number helper's
    variable-length output.

    Args:
        value: The amount to format.
        format: Babel pattern or named style.
        locale: Locale override, or ``None`` for the active one.

    Raises:
        ValueError: If ``locale`` is not a valid locale tag.
    """
    return format_decimal(value, format=format, locale=_babel_locale(locale))


def t_date(value: date | datetime, format: str = "medium", locale: str | Locale | None = None) -> str:  # noqa: A002  # pylint: disable=redefined-builtin
    """
    Format a date eagerly, returning a real ``str``.

    ``format`` is ``"short"``, ``"medium"``, ``"long"``, ``"full"``, or a
    Babel pattern.

    Args:
        value: The date (or datetime) to format.
        format: ``"short"``, ``"medium"``, ``"long"``, ``"full"`` or a Babel
            pattern.
        locale: Locale override, or ``None`` for the active one.

    Raises:
        ValueError: If ``locale`` is not a valid locale tag.
    """
    return format_date(value, format=format, locale=_babel_locale(locale))


def t_time(value: time | datetime, format: str = "short", locale: str | Locale | None = None, tz: tzinfo | str | None = None) -> str:  # noqa: A002  # pylint: disable=redefined-builtin
    """
    Format a time eagerly, returning a real ``str``.

    ``tz`` is applied to ``datetime`` values (a naive ``time`` is shown as-is,
    since ``time`` has no date to project onto a zone). When omitted, the
    timezone active at call time is used, which is always a concrete zone
    (:data:`~fastapi_simple_i18n.timezone.DEFAULT_TIMEZONE` by default); pass an
    explicit value to override it for this call alone.

    Args:
        value: The time (or datetime) to format.
        format: ``"short"``, ``"medium"``, ``"long"``, ``"full"`` or a Babel
            pattern.
        locale: Locale override, or ``None`` for the active one.
        tz: Timezone override (``tzinfo`` or IANA name), or ``None`` for the
            active one.

    Raises:
        ValueError: If ``locale`` is not a valid locale tag.
        ZoneInfoNotFoundError: If ``tz`` is an unknown IANA name.
    """
    return format_time(value, format=format, locale=_babel_locale(locale), tzinfo=_resolve_tz(tz))


def t_datetime(value: datetime, format: str = "medium", locale: str | Locale | None = None, tz: tzinfo | str | None = None) -> str:  # noqa: A002  # pylint: disable=redefined-builtin
    """
    Format a datetime eagerly, returning a real ``str``.

    ``tz`` is the zone the datetime is projected onto before formatting. When
    omitted, the timezone active at call time is used, which is always a
    concrete zone (:data:`~fastapi_simple_i18n.timezone.DEFAULT_TIMEZONE` by
    default, never the process local one); pass an explicit value to override it
    for this call alone.

    Args:
        value: The datetime to format.
        format: ``"short"``, ``"medium"``, ``"long"``, ``"full"`` or a Babel
            pattern.
        locale: Locale override, or ``None`` for the active one.
        tz: Timezone override (``tzinfo`` or IANA name), or ``None`` for the
            active one.

    Raises:
        ValueError: If ``locale`` is not a valid locale tag.
        ZoneInfoNotFoundError: If ``tz`` is an unknown IANA name.
    """
    return format_datetime(value, format=format, locale=_babel_locale(locale), tzinfo=_resolve_tz(tz))


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
#
# The formatters validate an explicit ``locale`` when they are built, not
# when they are read, so a mistyped locale is reported at the line that made
# the mistake rather than at an unrelated render.


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
            except (KeyError, IndexError, ValueError):
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

    def __init__(self, value: int | float | Decimal, *, format: str = "#,##0.###", locale: str | Locale | None = None) -> None:  # noqa: A002  # pylint: disable=redefined-builtin
        """
        Capture the value, format spec and optional explicit locale override.

        Args:
            value: The number to format.
            format: Babel pattern (default ``"#,##0.###"``) or a named style.
            locale: Optional locale override; defaults to the active locale
                at resolve time.

        Raises:
            ValueError: If ``locale`` is not a valid locale tag.
        """
        self._value = value
        self._format = format
        self._locale = resolve_locale(locale) if locale is not None else None

    def resolve(self) -> str:
        """
        Format the number against the active locale.
        """
        return format_decimal(self._value, format=self._format, locale=_babel_locale(self._locale))

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
    """
    A string-like wrapper that defers date formatting until rendered.

    The locale is read when ``__str__`` (or any other string operation) is
    called, so a value captured with one locale will re-render in
    whatever locale is active later.
    """

    __slots__ = ("_value", "_format", "_locale")

    def __init__(self, value: date | datetime, *, format: str = "medium", locale: str | Locale | None = None) -> None:  # noqa: A002  # pylint: disable=redefined-builtin
        """
        Capture the value, format spec and optional explicit locale override.

        Args:
            value: The date (or datetime) to format.
            format: ``"short"``, ``"medium"``, ``"long"``, ``"full"`` or a
                Babel pattern.
            locale: Optional locale override; defaults to the active locale
                at resolve time.

        Raises:
            ValueError: If ``locale`` is not a valid locale tag.
        """
        self._value = value
        self._format = format
        self._locale = resolve_locale(locale) if locale is not None else None

    def resolve(self) -> str:
        """
        Format the date against the active locale.
        """
        return format_date(self._value, format=self._format, locale=_babel_locale(self._locale))

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
    """
    A string-like wrapper that defers time formatting until rendered.

    The locale and the timezone are read when ``__str__`` (or any other
    string operation) is called, so a value captured with one locale will
    re-render in whatever locale is active later.
    """

    __slots__ = ("_value", "_format", "_locale", "_tz")

    def __init__(self, value: time | datetime, *, format: str = "short", locale: str | Locale | None = None, tz: tzinfo | str | None = None) -> None:  # noqa: A002  # pylint: disable=redefined-builtin
        """
        Capture the value, format spec, optional explicit locale override and optional explicit timezone override.

        Args:
            value: The time (or datetime) to format.
            format: ``"short"``, ``"medium"``, ``"long"``, ``"full"`` or a
                Babel pattern.
            locale: Optional locale override; defaults to the active locale
                at resolve time.
            tz: Optional timezone override (``tzinfo`` or IANA name); applied
                to ``datetime`` values only (a naive ``time`` is shown as-is).
                Defaults to the active timezone at resolve time, which is
                always a concrete zone.

        Raises:
            ValueError: If ``locale`` is not a valid locale tag.
            ZoneInfoNotFoundError: If ``tz`` is an unknown IANA name.
        """
        self._value = value
        self._format = format
        self._locale = resolve_locale(locale) if locale is not None else None
        self._tz = resolve_timezone(tz) if tz is not None else None

    def resolve(self) -> str:
        """
        Format the time against the active locale and timezone.
        """
        return format_time(self._value, format=self._format, locale=_babel_locale(self._locale), tzinfo=_resolve_tz(self._tz))

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
    """
    A string-like wrapper that defers datetime formatting until rendered.

    The locale and the timezone are read when ``__str__`` (or any other
    string operation) is called, so a value captured with one locale will
    re-render in whatever locale is active later.
    """

    __slots__ = ("_value", "_format", "_locale", "_tz")

    def __init__(self, value: datetime, *, format: str = "medium", locale: str | Locale | None = None, tz: tzinfo | str | None = None) -> None:  # noqa: A002  # pylint: disable=redefined-builtin
        """
        Capture the value, format spec, optional explicit locale override and optional explicit timezone override.

        Args:
            value: The datetime to format.
            format: ``"short"``, ``"medium"``, ``"long"``, ``"full"`` or a
                Babel pattern.
            locale: Optional locale override; defaults to the active locale
                at resolve time.
            tz: Optional timezone override (``tzinfo`` or IANA name) used to
                project the datetime before formatting. Defaults to the active
                timezone at resolve time, which is always a concrete zone.

        Raises:
            ValueError: If ``locale`` is not a valid locale tag.
            ZoneInfoNotFoundError: If ``tz`` is an unknown IANA name.
        """
        self._value = value
        self._format = format
        self._locale = resolve_locale(locale) if locale is not None else None
        self._tz = resolve_timezone(tz) if tz is not None else None

    def resolve(self) -> str:
        """
        Format the datetime against the active locale and timezone.
        """
        return format_datetime(self._value, format=self._format, locale=_babel_locale(self._locale), tzinfo=_resolve_tz(self._tz))

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


def lazy_t_number(value: int | float | Decimal, format: str = "#,##0.###", locale: str | Locale | None = None) -> LazyNumber:  # noqa: A002  # pylint: disable=redefined-builtin
    """
    Format a number lazily.

    Returns a string-like wrapper that formats the value against the
    locale active when the value is read.

    Args:
        value: The number to format.
        format: Babel pattern or named style.
        locale: Locale override, or ``None`` for the active one.

    Raises:
        ValueError: If ``locale`` is not a valid locale tag.
    """
    return LazyNumber(value, format=format, locale=locale)


def lazy_t_date(value: date | datetime, format: str = "medium", locale: str | Locale | None = None) -> LazyDate:  # noqa: A002  # pylint: disable=redefined-builtin
    """
    Format a date lazily.

    Returns a string-like wrapper that formats the value against the
    locale active when the value is read.

    Args:
        value: The date (or datetime) to format.
        format: ``"short"``, ``"medium"``, ``"long"``, ``"full"`` or a Babel
            pattern.
        locale: Locale override, or ``None`` for the active one.

    Raises:
        ValueError: If ``locale`` is not a valid locale tag.
    """
    return LazyDate(value, format=format, locale=locale)


def lazy_t_time(value: time | datetime, format: str = "short", locale: str | Locale | None = None, tz: tzinfo | str | None = None) -> LazyTime:  # noqa: A002  # pylint: disable=redefined-builtin
    """
    Format a time lazily.

    Returns a string-like wrapper that formats the value against the
    locale and timezone active when the value is read.

    Args:
        value: The time (or datetime) to format.
        format: ``"short"``, ``"medium"``, ``"long"``, ``"full"`` or a Babel
            pattern.
        locale: Locale override, or ``None`` for the active one.
        tz: Timezone override (``tzinfo`` or IANA name), or ``None`` for the
            active one.

    Raises:
        ValueError: If ``locale`` is not a valid locale tag.
    """
    return LazyTime(value, format=format, locale=locale, tz=tz)


def lazy_t_datetime(value: datetime, format: str = "medium", locale: str | Locale | None = None, tz: tzinfo | str | None = None) -> LazyDateTime:  # noqa: A002  # pylint: disable=redefined-builtin
    """
    Format a datetime lazily.

    Returns a string-like wrapper that formats the value against the
    locale and timezone active when the value is read.

    Args:
        value: The datetime to format.
        format: ``"short"``, ``"medium"``, ``"long"``, ``"full"`` or a Babel
            pattern.
        locale: Locale override, or ``None`` for the active one.
        tz: Timezone override (``tzinfo`` or IANA name), or ``None`` for the
            active one.

    Raises:
        ValueError: If ``locale`` is not a valid locale tag.
    """
    return LazyDateTime(value, format=format, locale=locale, tz=tz)


# --- Lazy money / amount helpers ----------------------------------------
#
# Mirror the eager ``t_money`` / ``t_amount`` helpers with string-like
# wrappers that defer the lookup until the value is rendered. Useful when
# a value is captured at module import time (a default-locale constant) and
# must re-render against whichever locale is active later.


class LazyMoney:
    """
    A string-like wrapper that defers currency formatting until rendered.

    Same fallback contract as :func:`t_money`: a missing or unrecognised
    ``currency`` degrades to a plain localised decimal rather than
    crashing. The locale is read when ``__str__`` (or any other string
    operation) is called, so a value captured with one locale will
    re-render in whatever locale is active later.
    """

    __slots__ = ("_value", "_currency", "_locale")

    def __init__(self, value: int | float | Decimal, *, currency: str = "", locale: str | Locale | None = None) -> None:
        """
        Capture the value, the optional currency code, and the optional explicit locale override.

        Args:
            value: The monetary amount.
            currency: ISO currency code (optional). Blank or unrecognised
                values fall back to a plain localised decimal.
            locale: Optional locale override; defaults to the active locale
                at resolve time.

        Raises:
            ValueError: If ``locale`` is not a valid locale tag.
        """
        self._value = value
        self._currency = currency
        self._locale = resolve_locale(locale) if locale is not None else None

    def resolve(self) -> str:
        """
        Format the amount against the active locale.
        """
        return _format_money(self._value, self._currency, _babel_locale(self._locale))

    def __str__(self) -> str:
        return self.resolve()

    def __repr__(self) -> str:
        return f"lazy_t_money({self._value!r})"

    def __format__(self, format_spec: str) -> str:
        return format(self.resolve(), format_spec)

    def __bool__(self) -> bool:
        return bool(self.resolve())

    def __add__(self, other: object) -> str:
        return self.resolve() + other  # type: ignore[operator]

    def __radd__(self, other: object) -> str:
        return other + self.resolve()  # type: ignore[operator]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, LazyMoney):
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


class LazyAmount:
    """
    A string-like wrapper that defers plain decimal formatting until rendered.

    No currency symbol — useful for aggregate sums that mix currencies. The
    locale is read when ``__str__`` (or any other string operation) is
    called, so a value captured with one locale will re-render in whatever
    locale is active later.
    """

    __slots__ = ("_value", "_format", "_locale")

    def __init__(self, value: int | float | Decimal, *, format: str = MONEY_FORMAT, locale: str | Locale | None = None) -> None:  # noqa: A002  # pylint: disable=redefined-builtin
        """
        Capture the value, the Babel format pattern, and the optional explicit locale override.

        Args:
            value: The decimal amount.
            format: Babel pattern (default :data:`MONEY_FORMAT`).
            locale: Optional locale override; defaults to the active locale
                at resolve time.

        Raises:
            ValueError: If ``locale`` is not a valid locale tag.
        """
        self._value = value
        self._format = format
        self._locale = resolve_locale(locale) if locale is not None else None

    def resolve(self) -> str:
        """
        Format the amount against the active locale.
        """
        return format_decimal(self._value, format=self._format, locale=_babel_locale(self._locale))

    def __str__(self) -> str:
        return self.resolve()

    def __repr__(self) -> str:
        return f"lazy_t_amount({self._value!r})"

    def __format__(self, format_spec: str) -> str:
        return format(self.resolve(), format_spec)

    def __bool__(self) -> bool:
        return bool(self.resolve())

    def __add__(self, other: object) -> str:
        return self.resolve() + other  # type: ignore[operator]

    def __radd__(self, other: object) -> str:
        return other + self.resolve()  # type: ignore[operator]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, LazyAmount):
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


def lazy_t_money(value: int | float | Decimal, currency: str = "", locale: str | Locale | None = None) -> LazyMoney:  # noqa: A002  # pylint: disable=redefined-builtin
    """
    Format a monetary amount lazily.

    Returns a string-like wrapper that formats the value against the
    locale active when the value is read. Same fallback contract as
    :func:`t_money` (blank or unrecognised ``currency`` degrades to a plain
    localised decimal).

    Args:
        value: The amount to format.
        currency: ISO currency code, or ``""`` for no currency.
        locale: Locale override, or ``None`` for the active one.

    Raises:
        ValueError: If ``locale`` is not a valid locale tag.
    """
    return LazyMoney(value, currency=currency, locale=locale)


def lazy_t_amount(value: int | float | Decimal, format: str = MONEY_FORMAT, locale: str | Locale | None = None) -> LazyAmount:  # noqa: A002  # pylint: disable=redefined-builtin
    """
    Format a plain decimal amount lazily.

    Returns a string-like wrapper that formats the value against the
    locale active when the value is read.

    Args:
        value: The amount to format.
        format: Babel pattern or named style.
        locale: Locale override, or ``None`` for the active one.

    Raises:
        ValueError: If ``locale`` is not a valid locale tag.
    """
    return LazyAmount(value, format=format, locale=locale)
