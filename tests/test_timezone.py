"""
Tests for the timezone context helpers.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest

from fastapi_simple_i18n.helpers import t_datetime
from fastapi_simple_i18n.timezone import (
    as_timezone,
    get_current_timezone,
    get_default_timezone,
    reset_current_timezone,
    resolve_timezone,
    set_current_timezone,
    set_default_timezone,
)


def test_resolve_timezone_returns_none_as_is():
    """
    ``None`` is returned untouched (used as the "no override" sentinel).
    """
    assert resolve_timezone(None) is None


def test_resolve_timezone_returns_tzinfo_as_is():
    """
    A ``tzinfo`` instance is returned untouched (no rewrapping).
    """
    value = ZoneInfo("UTC")
    assert resolve_timezone(value) is value


def test_resolve_timezone_parses_iana_name():
    """
    An IANA name is parsed into a ``ZoneInfo``.
    """
    resolved = resolve_timezone("Europe/Madrid")
    assert isinstance(resolved, ZoneInfo)
    assert str(resolved) == "Europe/Madrid"


def test_resolve_timezone_invalid_name_raises():
    """
    An unknown IANA name raises ``ZoneInfoNotFoundError``.
    """
    with pytest.raises(ZoneInfoNotFoundError):
        resolve_timezone("Not/A_Real_Zone")


def test_default_timezone_round_trip():
    """
    The default timezone is what ``get_default_timezone`` returns.
    """
    assert get_default_timezone() is None
    set_default_timezone("UTC")
    try:
        assert isinstance(get_default_timezone(), ZoneInfo)
    finally:
        set_default_timezone(None)
    assert get_default_timezone() is None


def test_default_timezone_accepts_tzinfo():
    """
    ``set_default_timezone`` accepts a ``tzinfo`` directly.
    """
    value = UTC
    set_default_timezone(value)
    try:
        assert get_default_timezone() is value
    finally:
        set_default_timezone(None)


def test_current_timezone_resolution_order():
    """
    The current timezone wins over the default; otherwise the default is used.
    """
    set_default_timezone("UTC")
    try:
        assert get_current_timezone() == ZoneInfo("UTC")

        token = set_current_timezone("Europe/Madrid")
        try:
            assert get_current_timezone() == ZoneInfo("Europe/Madrid")
        finally:
            reset_current_timezone(token)

        assert get_current_timezone() == ZoneInfo("UTC")
    finally:
        set_default_timezone(None)


def test_as_timezone_restores_on_exit():
    """
    ``as_timezone`` restores the previous value when the block exits, even on error.
    """
    set_default_timezone("UTC")
    try:
        with as_timezone("Europe/Madrid") as tz:
            assert tz == ZoneInfo("Europe/Madrid")
            assert get_current_timezone() == ZoneInfo("Europe/Madrid")
        assert get_current_timezone() == ZoneInfo("UTC")

        with pytest.raises(RuntimeError), as_timezone("Europe/Madrid"):
            raise RuntimeError("boom")
        assert get_current_timezone() == ZoneInfo("UTC")
    finally:
        set_default_timezone(None)


def test_as_timezone_accepts_none_to_clear():
    """
    Passing ``None`` clears the override inside the block.
    """
    with as_timezone("Europe/Madrid"):
        assert get_current_timezone() == ZoneInfo("Europe/Madrid")
        with as_timezone(None) as tz:
            assert tz is None
            assert get_current_timezone() is None
        assert get_current_timezone() == ZoneInfo("Europe/Madrid")


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


def test_datetime_helper_explicit_tz_wins():
    """
    An explicit ``tz`` argument overrides the active timezone.
    """
    naive = datetime(2024, 1, 1, 12, 0, 0)
    with as_timezone("UTC"):
        text = t_datetime(naive, format="yyyy-MM-dd HH:mm", tz="Europe/Madrid")
    assert text == "2024-01-01 13:00"
