"""
Tests for the timezone context helpers.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest

from fastapi_simple_i18n.helpers import lazy_t_datetime, t_datetime
from fastapi_simple_i18n.timezone import (
    DEFAULT_TIMEZONE,
    as_timezone,
    get_current_timezone,
    get_default_timezone,
    reset_current_timezone,
    resolve_timezone,
    set_current_timezone,
    set_default_timezone,
)

# --- resolution -------------------------------------------------------------


def test_default_timezone_is_utc():
    """
    The library starts in UTC, not in the process local zone.
    """
    assert ZoneInfo("UTC") == DEFAULT_TIMEZONE
    assert str(DEFAULT_TIMEZONE) == "UTC"


def test_resolve_timezone_returns_tzinfo_as_is():
    """
    A ``tzinfo`` instance is returned untouched (no rewrapping).
    """
    value = ZoneInfo("Europe/Madrid")
    assert resolve_timezone(value) is value


def test_resolve_timezone_parses_iana_name():
    """
    An IANA name is parsed into a ``ZoneInfo``.
    """
    resolved = resolve_timezone("Europe/Madrid")
    assert isinstance(resolved, ZoneInfo)
    assert str(resolved) == "Europe/Madrid"


def test_resolve_timezone_strips_blanks():
    """
    Surrounding whitespace is not part of the name.
    """
    assert resolve_timezone("  Europe/Madrid  ") == ZoneInfo("Europe/Madrid")


def test_resolve_timezone_of_utc_matches_the_default():
    """
    The default is the very object a caller passing ``"UTC"`` gets back.
    """
    assert resolve_timezone("UTC") is DEFAULT_TIMEZONE


def test_resolve_timezone_invalid_name_raises():
    """
    An unknown IANA name raises ``ZoneInfoNotFoundError``.
    """
    with pytest.raises(ZoneInfoNotFoundError):
        resolve_timezone("Not/A_Real_Zone")


@pytest.mark.parametrize("value", [None, 42, b"UTC", ["UTC"]])
def test_resolve_timezone_refuses_non_tzinfo(value):
    """
    Anything that is neither a ``tzinfo`` nor a string is reported.
    """
    with pytest.raises(TypeError, match="expected a timezone string"):
        resolve_timezone(value)


@pytest.mark.parametrize("value", ["", "   "])
def test_resolve_timezone_refuses_a_blank_name(value):
    """
    A blank name is reported instead of reaching the zone database.
    """
    with pytest.raises(ValueError, match="the value is empty"):
        resolve_timezone(value)


# --- the default ------------------------------------------------------------


def test_default_timezone_round_trip():
    """
    The default timezone is what ``get_default_timezone`` returns.

    It can be changed, and it always comes back as a real ``tzinfo``.
    """
    set_default_timezone("Europe/Madrid")
    assert get_default_timezone() == ZoneInfo("Europe/Madrid")
    assert get_current_timezone() == ZoneInfo("Europe/Madrid")
    set_default_timezone(DEFAULT_TIMEZONE)
    assert get_default_timezone() == DEFAULT_TIMEZONE


def test_default_timezone_accepts_tzinfo():
    """
    ``set_default_timezone`` accepts a ``tzinfo`` directly.
    """
    set_default_timezone(UTC)
    assert get_default_timezone() is UTC
    assert get_current_timezone() is UTC


@pytest.mark.parametrize("caller", [set_default_timezone, set_current_timezone])
def test_setters_refuse_none(caller):
    """
    A timezone is always in effect, so there is no way to unset one.
    """
    with pytest.raises(TypeError, match="Invalid timezone None"):
        caller(None)


def test_default_timezone_refuses_a_broken_name():
    """
    A bad default is reported where it was set, not when it is used.
    """
    with pytest.raises(ZoneInfoNotFoundError):
        set_default_timezone("Not/A_Real_Zone")
    assert get_default_timezone() == DEFAULT_TIMEZONE


# --- the current timezone ---------------------------------------------------


def test_current_timezone_never_none():
    """
    With nothing configured at all, there is still a timezone.
    """
    assert get_current_timezone() is DEFAULT_TIMEZONE
    assert isinstance(get_current_timezone(), ZoneInfo)


def test_current_timezone_resolution_order():
    """
    The current timezone wins over the default; otherwise the default is used.
    """
    set_default_timezone("UTC")
    assert get_current_timezone() == ZoneInfo("UTC")

    token = set_current_timezone("Europe/Madrid")
    assert get_current_timezone() == ZoneInfo("Europe/Madrid")
    reset_current_timezone(token)

    assert get_current_timezone() == ZoneInfo("UTC")


def test_current_timezone_is_independent_of_the_default():
    """
    A current timezone set before the default changes still wins.
    """
    token = set_current_timezone("Asia/Tokyo")
    set_default_timezone("Europe/Madrid")
    assert get_current_timezone() == ZoneInfo("Asia/Tokyo")
    reset_current_timezone(token)
    assert get_current_timezone() == ZoneInfo("Europe/Madrid")


# --- as_timezone ------------------------------------------------------------


def test_as_timezone_restores_on_exit():
    """
    ``as_timezone`` restores the previous value when the block exits, even on error.
    """
    with as_timezone("Europe/Madrid") as tz:
        assert tz == ZoneInfo("Europe/Madrid")
        assert get_current_timezone() == ZoneInfo("Europe/Madrid")
    assert get_current_timezone() == DEFAULT_TIMEZONE

    with pytest.raises(RuntimeError), as_timezone("Europe/Madrid"):
        raise RuntimeError("boom")
    assert get_current_timezone() == DEFAULT_TIMEZONE


def test_as_timezone_nests():
    """
    Nested blocks restore in the right order.
    """
    with as_timezone("Europe/Madrid"):
        with as_timezone("Asia/Tokyo"):
            assert get_current_timezone() == ZoneInfo("Asia/Tokyo")
        assert get_current_timezone() == ZoneInfo("Europe/Madrid")
    assert get_current_timezone() == DEFAULT_TIMEZONE


def test_as_timezone_refuses_none():
    """
    There is no way to clear the timezone for a block any more.
    """
    with pytest.raises(TypeError, match="Invalid timezone None"), as_timezone(None):
        pass  # pragma: no cover
    assert get_current_timezone() == DEFAULT_TIMEZONE


def test_as_timezone_validates_on_entry():
    """
    A bad name is reported when the block is entered, before anything runs.
    """
    with pytest.raises(ZoneInfoNotFoundError), as_timezone("Not/A_Real_Zone"):
        pass  # pragma: no cover
    assert get_current_timezone() == DEFAULT_TIMEZONE


# --- helpers ----------------------------------------------------------------


def test_datetime_helper_respects_timezone():
    """
    ``t_datetime`` uses the active timezone when projecting a naive datetime.
    """
    naive = datetime(2024, 1, 1, 12, 0, 0)
    with as_timezone("UTC"):
        utc_text = t_datetime(naive, format="yyyy-MM-dd HH:mm")
    with as_timezone("Europe/Madrid"):
        madrid_text = t_datetime(naive, format="yyyy-MM-dd HH:mm")
    assert utc_text == "2024-01-01 12:00"
    assert madrid_text == "2024-01-01 13:00"


def test_datetime_helper_defaults_to_utc():
    """
    With no timezone configured, a naive datetime is read as UTC.
    """
    naive = datetime(2024, 1, 1, 12, 0, 0)
    assert t_datetime(naive, format="yyyy-MM-dd HH:mm") == "2024-01-01 12:00"
    assert t_datetime(naive, format="yyyy-MM-dd HH:mm", tz="UTC") == "2024-01-01 12:00"


def test_datetime_helper_explicit_tz_wins():
    """
    An explicit ``tz`` argument overrides the active timezone.
    """
    naive = datetime(2024, 1, 1, 12, 0, 0)
    with as_timezone("UTC"):
        text = t_datetime(naive, format="yyyy-MM-dd HH:mm", tz="Europe/Madrid")
    assert text == "2024-01-01 13:00"


def test_datetime_helper_validates_tz():
    """
    A bad ``tz`` override is reported by the eager helper and by the lazy one.
    """
    naive = datetime(2024, 1, 1, 12, 0, 0)
    with pytest.raises(ZoneInfoNotFoundError):
        t_datetime(naive, tz="Not/A_Real_Zone")
    with pytest.raises(ZoneInfoNotFoundError):
        lazy_t_datetime(naive, tz="Not/A_Real_Zone")
