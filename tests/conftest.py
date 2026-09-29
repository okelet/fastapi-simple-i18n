"""
Shared pytest fixtures and state reset for the test suite.
"""

import pytest

from fastapi_simple_i18n import registry
from fastapi_simple_i18n.locale import current_locale, set_current_locale, set_default_locale
from fastapi_simple_i18n.manager import TranslationManager
from fastapi_simple_i18n.models import TranslationEntry
from fastapi_simple_i18n.registry import set_translation_manager
from fastapi_simple_i18n.timezone import current_timezone, set_default_timezone


@pytest.fixture(autouse=True)
def reset_global_state():
    """
    Reset the process-wide manager, default locale, current locale, and
    default timezone.

    Runs before and after every test so tests do not leak state into each other.
    """
    registry._current_manager = None  # noqa: SLF001  # pylint: disable=protected-access
    set_default_locale("en")
    set_default_timezone(None)
    current_locale.set("")
    current_timezone.set(None)
    yield
    registry._current_manager = None  # noqa: SLF001  # pylint: disable=protected-access
    set_default_locale("en")
    set_default_timezone(None)
    current_locale.set("")
    current_timezone.set(None)


@pytest.fixture(name="sample_entries")
def sample_entries_fixture() -> list[TranslationEntry]:
    """
    Return a representative set of Spanish entries used across tests.
    """
    return [
        TranslationEntry(key="Yes", value="Sí"),
        TranslationEntry(key="Archive", value="Archivar", variant="verb"),
        TranslationEntry(key="Archive", value="Archivo", variant="noun"),
        TranslationEntry(key="My items", value="Mis elementos", draft=True),
        TranslationEntry(key="There are {item_count} items", value="Hay {item_count} elementos"),
    ]


@pytest.fixture(name="manager")
def manager_fixture(sample_entries: list[TranslationEntry]) -> TranslationManager:
    """
    Return a manager preloaded with Spanish entries and activated globally.
    """
    manager = TranslationManager(builtin_locale="en")
    manager.add_entries("es", sample_entries)
    set_translation_manager(manager)
    set_current_locale("es")
    return manager
