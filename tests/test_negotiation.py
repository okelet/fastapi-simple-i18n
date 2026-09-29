"""
Tests for Accept-Language parsing and locale negotiation.
"""

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
    assert negotiate_locale("es", {"es", "fr"}, "en") == "es"


def test_negotiate_base_language_match():
    """
    A regional variant matches its base language.
    """
    assert negotiate_locale("es-ES,es;q=0.9", {"es"}, "en") == "es"


def test_negotiate_falls_back_to_default():
    """
    When nothing matches, the default locale is returned.
    """
    assert negotiate_locale("de,it;q=0.5", {"es", "fr"}, "en") == "en"


def test_negotiate_case_insensitive():
    """
    Matching is case-insensitive and normalizes separators.
    """
    assert negotiate_locale("ES_es", {"es"}, "en") == "es"
