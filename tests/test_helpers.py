"""
Tests for the translation and formatting helpers.

Covers both flavours of every helper:

* ``t`` / ``t_number`` / ``t_date`` / ``t_time`` / ``t_datetime`` are
  eager — they capture the locale at call time and return a real ``str``.
* ``lazy_t`` / ``lazy_t_number`` / ``lazy_t_date`` / ``lazy_t_time`` /
  ``lazy_t_datetime`` are lazy — they return string-like wrappers that
  read the locale at render time.
"""

from datetime import date, datetime, time

import pytest

from fastapi_simple_i18n.helpers import (
    LazyDate,
    LazyDateTime,
    LazyNumber,
    LazyTime,
    LazyTranslatableStr,
    TranslatableStr,
    lazy_t,
    lazy_t_date,
    lazy_t_datetime,
    lazy_t_number,
    lazy_t_time,
    t,
    t_date,
    t_datetime,
    t_number,
    t_time,
)
from fastapi_simple_i18n.locale import set_current_locale
from fastapi_simple_i18n.manager import TranslationManager

# --- Eager helpers ---


def test_t_returns_a_str(manager: TranslationManager):
    """t() returns a str subclass carrying the translated text."""
    result = t("Yes")
    assert isinstance(result, str)
    assert isinstance(result, TranslatableStr)


def test_t_resolves_eagerly(manager: TranslationManager):
    """The lookup uses the locale active at call time."""
    set_current_locale("en")
    assert t("Yes") == "Yes"
    set_current_locale("es")
    assert t("Yes") == "Sí"


def test_t_str_alias(manager: TranslationManager):
    """The return value works wherever a string is expected."""
    set_current_locale("es")
    translated = t("Yes")
    assert str(translated) == "Sí"
    assert translated == "Sí"
    assert ("prefix " + t("Yes")) == "prefix Sí"
    assert t("Yes") in ("Sí", "no")


def test_t_variant(manager: TranslationManager):
    """The _variant argument is forwarded to the manager."""
    assert t("Archive", _variant="noun") == "Archivo"
    assert t("Archive", _variant="verb") == "Archivar"


def test_t_format_params(manager: TranslationManager):
    """Named parameters are applied with str.format at call time."""
    assert t("There are {item_count} items", item_count=3) == "Hay 3 elementos"


def test_t_equality_with_string(manager: TranslationManager):
    """A translation compares equal to its resolved string and is hashable."""
    assert t("Yes") == "Sí"
    assert t("Yes") == t("Yes")
    assert {t("Yes"), "Sí"} == {"Sí"}


def test_t_without_manager_raises():
    """Using t() without a configured manager raises a clear error."""
    with pytest.raises(RuntimeError, match="No TranslationManager configured"):
        t("Yes")


def test_t_number_locale_aware(manager: TranslationManager):
    """t_number formats per locale."""
    set_current_locale("es")
    assert t_number(1234.5) == "1.234,5"
    set_current_locale("en")
    assert t_number(1234.5) == "1,234.5"


def test_t_date_locale_aware(manager: TranslationManager):
    """t_date formats per locale."""
    set_current_locale("en")
    assert t_date(date(2026, 8, 30)) == "Aug 30, 2026"


def test_t_time_and_datetime(manager: TranslationManager):
    """t_time and t_datetime format without error."""
    set_current_locale("en")
    assert t_time(time(14, 30))
    assert t_datetime(datetime(2026, 8, 30, 14, 30))


# --- Lazy helpers ---


def test_lazy_t_returns_a_lazy_translatable_str(manager: TranslationManager):
    """lazy_t returns a LazyTranslatableStr, not a plain str."""
    set_current_locale("es")
    result = lazy_t("Yes")
    assert isinstance(result, LazyTranslatableStr)
    # Critical: it must NOT be a str subclass — that is what lets json.dumps
    # and the C-level str protocol fail when the wrong shape sneaks in.
    assert not isinstance(result, str)


def test_lazy_t_resolves_at_render_time(manager: TranslationManager):
    """lazy_t reads the locale active when the value is read."""
    set_current_locale("en")
    lazy = lazy_t("Yes")
    assert str(lazy) == "Yes"
    set_current_locale("es")
    assert str(lazy) == "Sí"


def test_lazy_t_string_dunders(manager: TranslationManager):
    """lazy_t behaves like a string in the dunders people actually use."""
    set_current_locale("es")
    lazy = lazy_t("Yes")

    assert str(lazy) == "Sí"
    assert f"{lazy}" == "Sí"
    assert f"{lazy:>5}" == "   Sí"
    assert ("X: " + lazy) == "X: Sí"
    assert (lazy + " Z") == "Sí Z"
    assert lazy * 2 == "SíSí"
    assert "í" in lazy
    assert len(lazy) == 2
    assert lazy[0] == "S"
    assert list(lazy) == ["S", "í"]
    assert lazy == "Sí"
    assert lazy == lazy_t("Yes")
    assert lazy != "No"
    assert hash(lazy) == hash("Sí")

    # Used in a template / format string.
    assert f"{lazy} world" == "Sí world"
    assert f"Yes {lazy}" == "Yes Sí"


def test_lazy_t_variant_and_params(manager: TranslationManager):
    """Variant and format params are forwarded to the manager."""
    set_current_locale("es")
    assert str(lazy_t("Archive", _variant="noun")) == "Archivo"
    assert str(lazy_t("Archive", _variant="verb")) == "Archivar"
    assert str(lazy_t("There are {item_count} items", item_count=4)) == "Hay 4 elementos"


def test_lazy_t_resolves_eagerly_per_call(manager: TranslationManager):
    """The same lazy_t object can render in different locales at different times."""
    lazy = lazy_t("Yes")
    set_current_locale("en")
    assert str(lazy) == "Yes"
    set_current_locale("es")
    assert str(lazy) == "Sí"
    set_current_locale("en")
    assert str(lazy) == "Yes"


def test_lazy_t_needs_str_at_json_boundary(manager: TranslationManager):
    """lazy_t is not JSON-serializable as-is — wrap with str() at the boundary.

    This documents the cost of going lazy: str/json/Pydantic boundaries need
    an explicit str(). The eager form does not.
    """
    import json

    set_current_locale("es")
    with pytest.raises(TypeError, match="JSON serializable"):
        json.dumps({"msg": lazy_t("Yes")})
    # ensure_ascii=False so the assertion is readable; the default would
    # escape "í" as \u00ed.
    assert json.dumps({"msg": str(lazy_t("Yes"))}, ensure_ascii=False) == '{"msg": "Sí"}'


def test_lazy_t_number(manager: TranslationManager):
    """lazy_t_number returns a LazyNumber that re-formats per locale at render."""
    set_current_locale("es")
    lazy = lazy_t_number(1234.5)
    assert isinstance(lazy, LazyNumber)
    assert not isinstance(lazy, str)
    assert str(lazy) == "1.234,5"
    assert lazy == "1.234,5"
    set_current_locale("en")
    assert str(lazy) == "1,234.5"


def test_lazy_t_date(manager: TranslationManager):
    """lazy_t_date returns a LazyDate that re-formats per locale at render."""
    set_current_locale("en")
    lazy = lazy_t_date(date(2026, 8, 30))
    assert isinstance(lazy, LazyDate)
    assert str(lazy) == "Aug 30, 2026"
    set_current_locale("es")
    # Spanish medium date format, exact text may vary across Babel versions.
    assert str(lazy).startswith("30")  # e.g. "30 ago 2026"


def test_lazy_t_time(manager: TranslationManager):
    """lazy_t_time returns a LazyTime that re-formats per locale at render."""
    set_current_locale("en")
    lazy = lazy_t_time(time(14, 30))
    assert isinstance(lazy, LazyTime)
    assert "30" in str(lazy)
    set_current_locale("es")
    assert str(lazy) == "14:30"


def test_lazy_t_datetime(manager: TranslationManager):
    """lazy_t_datetime returns a LazyDateTime that re-formats per locale at render."""
    moment = datetime(2026, 8, 30, 14, 30)
    set_current_locale("en")
    lazy = lazy_t_datetime(moment, "short")
    assert isinstance(lazy, LazyDateTime)
    assert "30" in str(lazy)
    set_current_locale("es")
    assert str(lazy) == "30/8/26, 14:30"


def test_lazy_formatters_have_explicit_locale_override(manager: TranslationManager):
    """An explicit ``locale`` argument pins the format regardless of current."""
    moment = datetime(2026, 8, 30, 14, 30)
    set_current_locale("en")
    assert str(lazy_t_datetime(moment, "short", locale="es")) == "30/8/26, 14:30"
    set_current_locale("es")
    assert str(lazy_t_datetime(moment, "short", locale="en")).startswith("8/30/26")
