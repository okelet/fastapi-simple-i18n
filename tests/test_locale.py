"""
Tests for the locale context management helpers.
"""

import pytest

from fastapi_simple_i18n.locale import (
    as_locale,
    get_current_locale,
    get_default_locale,
    reset_current_locale,
    set_current_locale,
    set_default_locale,
)


def test_default_locale_when_nothing_set():
    """
    With no forced locale, the default locale is returned.
    """
    set_default_locale("en")
    assert get_current_locale() == "en"


def test_set_current_locale_overrides_default():
    """
    A forced locale takes precedence over the default.
    """
    set_default_locale("en")
    set_current_locale("es")
    assert get_current_locale() == "es"


def test_reset_current_locale_restores_previous():
    """
    Resetting with the returned token restores the previous value.
    """
    set_default_locale("en")
    token = set_current_locale("fr")
    assert get_current_locale() == "fr"
    reset_current_locale(token)
    assert get_current_locale() == "en"


def test_get_default_locale():
    """
    get_default_locale reflects the configured default.
    """
    set_default_locale("de")
    assert get_default_locale() == "de"


def test_as_locale_activates_and_restores():
    """
    as_locale sets the locale inside the block and restores it on exit.
    """
    set_default_locale("en")
    set_current_locale("es")
    with as_locale("fr") as loc:
        assert loc == "fr"
        assert get_current_locale() == "fr"
    assert get_current_locale() == "es"


def test_as_locale_restores_on_exception():
    """
    as_locale restores the previous locale even if the block raises.
    """
    set_default_locale("en")
    set_current_locale("es")
    with pytest.raises(ValueError), as_locale("fr"):
        raise ValueError("boom")
    assert get_current_locale() == "es"


def test_as_locale_nested():
    """
    Nested as_locale blocks restore the correct enclosing locale.
    """
    set_default_locale("en")
    with as_locale("es"):
        assert get_current_locale() == "es"
        with as_locale("fr"):
            assert get_current_locale() == "fr"
        assert get_current_locale() == "es"
    assert get_current_locale() == "en"
