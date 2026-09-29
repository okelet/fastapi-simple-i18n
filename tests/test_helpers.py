"""
Tests for the lazy translation helpers and Babel formatting.
"""

from datetime import date, datetime, time

import pytest

from fastapi_simple_i18n.helpers import (
    LazyTranslation,
    t,
    t_date,
    t_datetime,
    t_number,
    t_time,
)
from fastapi_simple_i18n.locale import set_current_locale
from fastapi_simple_i18n.manager import TranslationManager


def test_t_returns_lazy_translation(manager: TranslationManager):
    """
    t() returns a LazyTranslation, not a plain string.
    """
    result = t("Yes")
    assert isinstance(result, LazyTranslation)


def test_lazy_resolves_on_str(manager: TranslationManager):
    """
    A lazy translation resolves to the value when converted to a string.
    """
    assert str(t("Yes")) == "Sí"


def test_lazy_uses_locale_at_render_time(manager: TranslationManager):
    """
    The locale is read when the lazy translation is rendered, not created.
    """
    lazy = t("Yes")
    set_current_locale("en")
    assert str(lazy) == "Yes"
    set_current_locale("es")
    assert str(lazy) == "Sí"


def test_lazy_variant(manager: TranslationManager):
    """
    The _variant argument is forwarded to the manager.
    """
    assert str(t("Archive", _variant="noun")) == "Archivo"
    assert str(t("Archive", _variant="verb")) == "Archivar"


def test_lazy_format_params(manager: TranslationManager):
    """
    Named parameters are applied with str.format at render time.
    """
    assert str(t("There are {item_count} items", item_count=3)) == "Hay 3 elementos"


def test_lazy_equality_with_string(manager: TranslationManager):
    """
    A lazy translation compares equal to its resolved string.
    """
    assert t("Yes") == "Sí"


def test_lazy_resolve_explicit_locale(manager: TranslationManager):
    """
    resolve() accepts an explicit locale overriding the current one.
    """
    assert t("Yes").resolve(locale="en") == "Yes"


def test_t_number_locale_aware(manager: TranslationManager):
    """
    Numbers are formatted per locale.
    """
    set_current_locale("es")
    assert t_number(1234.5) == "1.234,5"
    set_current_locale("en")
    assert t_number(1234.5) == "1,234.5"


def test_t_date_locale_aware(manager: TranslationManager):
    """
    Dates are formatted per locale.
    """
    set_current_locale("en")
    assert t_date(date(2026, 8, 30)) == "Aug 30, 2026"


def test_t_time_and_datetime(manager: TranslationManager):
    """
    Time and datetime helpers format without error.
    """
    set_current_locale("en")
    assert t_time(time(14, 30))
    assert t_datetime(datetime(2026, 8, 30, 14, 30))


def test_t_without_manager_raises():
    """
    Using t() without a configured manager raises a clear error.
    """
    with pytest.raises(RuntimeError, match="No TranslationManager configured"):
        str(t("Yes"))
