"""
Tests for TranslationManager resolution logic.
"""

from fastapi_simple_i18n.manager import TranslationManager
from fastapi_simple_i18n.models import Translation, TranslationEntry


def make_manager() -> TranslationManager:
    """
    Build a manager preloaded with Spanish entries.
    """
    manager = TranslationManager(builtin_locale="en")
    manager.add_entries(
        "es",
        [
            TranslationEntry(key="Yes", value="Sí"),
            TranslationEntry(key="Archive", value="Archivar", variant="verb"),
            TranslationEntry(key="Archive", value="Archivo", variant="noun"),
            TranslationEntry(key="My items", value="Mis elementos", draft=True),
        ],
    )
    return manager


def test_translate_simple():
    """
    A known key resolves to its value.
    """
    assert make_manager().translate("Yes", locale="es") == "Sí"


def test_translate_variant():
    """
    Variants disambiguate identical keys.
    """
    manager = make_manager()
    assert manager.translate("Archive", variant="verb", locale="es") == "Archivar"
    assert manager.translate("Archive", variant="noun", locale="es") == "Archivo"


def test_translate_missing_variant_falls_back_to_key():
    """
    Requesting a key without a variant when only variants exist falls back.
    """
    assert make_manager().translate("Archive", locale="es") == "Archive"


def test_translate_draft_is_used():
    """
    Draft entries are used at runtime.
    """
    assert make_manager().translate("My items", locale="es") == "Mis elementos"


def test_translate_missing_key_falls_back_to_key():
    """
    An unknown key falls back to the key itself.
    """
    assert make_manager().translate("Unknown", locale="es") == "Unknown"


def test_builtin_locale_returns_key_verbatim():
    """
    The built-in locale returns keys unchanged and ignores variants.
    """
    manager = make_manager()
    assert manager.translate("Yes", locale="en") == "Yes"
    assert manager.translate("Archive", variant="noun", locale="en") == "Archive"


def test_builtin_locale_default_when_none():
    """
    A None locale resolves as the built-in locale.
    """
    assert make_manager().translate("Yes") == "Yes"


def test_supported_locales_includes_builtin():
    """
    supported_locales always includes the built-in locale.
    """
    assert make_manager().supported_locales() == {"en", "es"}


def test_add_translation_merges_locales():
    """
    Adding a second Translation for the same locale merges entries.
    """
    manager = TranslationManager(builtin_locale="en")
    manager.add_translation(Translation("es", [TranslationEntry(key="Yes", value="Sí")]))
    manager.add_translation(Translation("es", [TranslationEntry(key="No", value="No")]))
    assert manager.translate("Yes", locale="es") == "Sí"
    assert manager.translate("No", locale="es") == "No"


def test_custom_builtin_locale():
    """
    The built-in locale can be a language other than English.
    """
    manager = TranslationManager(builtin_locale="es")
    manager.add_entries("en", [TranslationEntry(key="Sí", value="Yes")])
    assert manager.translate("Sí", locale="es") == "Sí"
    assert manager.translate("Sí", locale="en") == "Yes"
