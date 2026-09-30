"""
Tests for locale resolution and the locale context management helpers.
"""

import pytest
from babel.core import Locale
from babel.localedata import locale_identifiers

from fastapi_simple_i18n.locale import (
    as_locale,
    get_current_locale,
    get_default_locale,
    reset_current_locale,
    resolve_locale,
    set_current_locale,
    set_default_locale,
)


def test_default_locale_when_nothing_set():
    """
    With no forced locale, the default locale is returned.
    """
    set_default_locale("en")
    assert get_current_locale() == Locale("en")


def test_set_current_locale_overrides_default():
    """
    A forced locale takes precedence over the default.
    """
    set_default_locale("en")
    set_current_locale("es")
    assert get_current_locale() == Locale("es")


def test_reset_current_locale_restores_previous():
    """
    Resetting with the returned token restores the previous value.
    """
    set_default_locale("en")
    token = set_current_locale("fr")
    assert get_current_locale() == Locale("fr")
    reset_current_locale(token)
    assert get_current_locale() == Locale("en")


def test_get_default_locale():
    """
    get_default_locale reflects the configured default.
    """
    set_default_locale("de")
    assert get_default_locale() == Locale("de")


def test_as_locale_activates_and_restores():
    """
    as_locale sets the locale inside the block and restores it on exit.
    """
    set_default_locale("en")
    set_current_locale("es")
    with as_locale("fr") as loc:
        assert loc == Locale("fr")
        assert get_current_locale() == Locale("fr")
    assert get_current_locale() == Locale("es")


def test_as_locale_restores_on_exception():
    """
    as_locale restores the previous locale even if the block raises.
    """
    set_default_locale("en")
    set_current_locale("es")
    with pytest.raises(ValueError), as_locale("fr"):
        raise ValueError("boom")
    assert get_current_locale() == Locale("es")


def test_as_locale_nested():
    """
    Nested as_locale blocks restore the correct enclosing locale.
    """
    set_default_locale("en")
    with as_locale("es"):
        assert get_current_locale() == Locale("es")
        with as_locale("fr"):
            assert get_current_locale() == Locale("fr")
        assert get_current_locale() == Locale("es")
    assert get_current_locale() == Locale("en")


def test_current_locale_is_a_locale_object():
    """
    get_current_locale returns a babel Locale, never a string and never None.
    """
    set_default_locale("en")
    set_current_locale("pt-br")
    active = get_current_locale()
    assert isinstance(active, Locale)
    assert str(active) == "pt_BR"
    assert active.language == "pt"
    assert active.territory == "BR"


def test_default_locale_is_stored_as_a_locale_object():
    """
    The default locale is resolved on the way in, so no spelling survives.
    """
    set_default_locale("EN-us")
    assert get_default_locale() == Locale("en", territory="US")
    assert str(get_default_locale()) == "en_US"


# --- resolve_locale ---


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("es", Locale("es")),
        ("es_ES", Locale("es", territory="ES")),
        ("es-ES", Locale("es", territory="ES")),
        ("ES-es", Locale("es", territory="ES")),
        ("pt_BR", Locale("pt", territory="BR")),
        ("zh-hans-cn", Locale("zh", script="Hans", territory="CN")),
        ("es_419", Locale("es", territory="419")),
        ("en_US_POSIX", Locale("en", territory="US", variant="POSIX")),
        ("  fr  ", Locale("fr")),
    ],
)
def test_resolve_locale_accepts_every_spelling(value, expected):
    """
    Both separators, any casing and surrounding blanks resolve to one locale.
    """
    assert resolve_locale(value) == expected


def test_resolve_locale_returns_a_locale_object():
    """
    Resolution always yields a babel Locale, whatever the input spelling.
    """
    resolved = resolve_locale("EN-us")
    assert isinstance(resolved, Locale)
    assert str(resolved) == "en_US"
    assert resolved.get_display_name() == "English (United States)"


def test_resolve_locale_passes_a_locale_through():
    """
    A Locale instance is returned unchanged, without re-parsing.
    """
    locale = Locale("it", territory="IT")
    assert resolve_locale(locale) is locale


def test_resolve_locale_normalizes_equal_spellings():
    """
    Two spellings of the same locale are equal once resolved.
    """
    assert resolve_locale("pt-br") == resolve_locale("pt_BR") == Locale("pt", territory="BR")


def test_resolve_locale_rejects_mixed_separators():
    """
    Mixing both separators is rejected instead of silently mis-parsed.
    """
    with pytest.raises(ValueError, match="single separator"):
        resolve_locale("en_US-POSIX")


def test_resolve_locale_rejects_an_empty_value():
    """
    An empty or blank value is rejected.
    """
    with pytest.raises(ValueError, match="empty"):
        resolve_locale("   ")


def test_resolve_locale_rejects_a_malformed_tag():
    """
    A tag that is not a locale identifier at all is rejected.
    """
    with pytest.raises(ValueError, match="Invalid locale 'english'"):
        resolve_locale("english")


def test_resolve_locale_rejects_an_unknown_locale():
    """
    A well-formed tag CLDR does not know is rejected.
    """
    with pytest.raises(ValueError, match="xx_YY"):
        resolve_locale("xx_YY")


def test_resolve_locale_rejects_a_non_string():
    """
    Anything that is not a string or a Locale is rejected.
    """
    with pytest.raises(ValueError, match="expected a locale string, got int"):
        resolve_locale(42)  # type: ignore[arg-type]


def test_set_default_locale_validates():
    """
    set_default_locale rejects an unusable locale instead of storing it.
    """
    with pytest.raises(ValueError, match="Invalid locale"):
        set_default_locale("not-a-locale")


def test_set_current_locale_validates():
    """
    set_current_locale rejects an unusable locale instead of storing it.
    """
    with pytest.raises(ValueError, match="Invalid locale"):
        set_current_locale("xx")


def test_as_locale_validates_before_entering():
    """
    as_locale rejects an unusable locale without touching the context.
    """
    set_default_locale("en")
    with pytest.raises(ValueError, match="Invalid locale"), as_locale("nope"):
        pass  # pragma: no cover - the block must not be reached
    assert get_current_locale() == Locale("en")


def test_every_cldr_locale_resolves():
    """
    Every locale CLDR names resolves through the same entry point.

    So no tag the library is likely to meet is rejected.
    """
    identifiers = sorted(locale_identifiers())
    assert identifiers
    for identifier in identifiers:
        assert isinstance(resolve_locale(identifier), Locale)
