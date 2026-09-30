"""
Tests for Accept-Language parsing and locale negotiation.
"""

import pytest
from babel.core import Locale

from fastapi_simple_i18n.negotiation import negotiate_locale, parse_accept_language


def test_parse_accept_language_orders_by_quality():
    """
    Locales are returned ordered by descending quality.
    """
    assert parse_accept_language("es-ES,es;q=0.9,en;q=0.8") == ["es-ES", "es", "en"]


def test_parse_accept_language_empty():
    """
    An empty header yields an empty list.
    """
    assert parse_accept_language("") == []


def test_negotiate_exact_match():
    """
    An exact supported locale is chosen.
    """
    assert negotiate_locale("es", {"es", "fr"}, "en") == Locale("es")


def test_negotiate_base_language_match():
    """
    A regional variant matches its base language.
    """
    assert negotiate_locale("es-ES,es;q=0.9", {"es"}, "en") == Locale("es")


def test_negotiate_falls_back_to_default():
    """
    When nothing matches, the default locale is returned.
    """
    assert negotiate_locale("de,it;q=0.5", {"es", "fr"}, "en") == Locale("en")


def test_negotiate_case_insensitive():
    """
    Matching is case-insensitive and normalizes separators.
    """
    assert negotiate_locale("ES_es", {"es"}, "en") == Locale("es")


def test_negotiate_returns_a_locale_object():
    """
    The negotiated value is a babel Locale, whatever the supported spelling.
    """
    negotiated = negotiate_locale("pt-BR", {"pt_BR"}, "en")
    assert isinstance(negotiated, Locale)
    assert str(negotiated) == "pt_BR"


def test_negotiate_matches_a_composite_supported_locale():
    """
    A composite supported locale is selected by any spelling of itself.
    """
    assert negotiate_locale("PT-br", {"pt-BR", "en"}, "en") == Locale("pt", territory="BR")


def test_negotiate_skips_entries_that_are_not_locales():
    """
    A wildcard or a malformed entry is skipped, not treated as a match.
    """
    assert negotiate_locale("*,xx;q=0.9,en-*;q=0.8", {"es", "fr"}, "en") == Locale("en")


def test_negotiate_does_not_guess_a_region():
    """
    A regional candidate never lands on a supported locale of another region.
    """
    assert negotiate_locale("es-MX", {"es_ES", "fr"}, "en") == Locale("en")


def test_negotiate_validates_the_default_locale():
    """
    An unusable default locale is reported instead of silently returned.
    """
    with pytest.raises(ValueError, match="Invalid locale 'nope'"):
        negotiate_locale("de", {"es"}, "nope")
