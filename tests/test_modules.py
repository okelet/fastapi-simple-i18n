"""
Tests for BaseModuleTranslation and manager.register_translation.
"""

from pathlib import Path

from babel.core import Locale

from fastapi_simple_i18n.manager import TranslationManager
from fastapi_simple_i18n.models import TranslationEntry, dump_translation_file
from fastapi_simple_i18n.modules import DEFAULT_TEMPLATE_SUFFIXES, BaseModuleTranslation, has_suffix


def build_module(tmp_path: Path) -> type[BaseModuleTranslation]:
    """
    Create a module translation class rooted at a temp directory with es/fr files.
    """
    translations_dir = tmp_path / "translations"
    dump_translation_file([TranslationEntry(key="Yes", value="Sí")], translations_dir / "es.json")
    dump_translation_file([TranslationEntry(key="Yes", value="Oui")], translations_dir / "fr.json")

    class TempModule(BaseModuleTranslation):
        """
        Module translation rooted at the temp directory.
        """

        @classmethod
        def get_source_dirs(cls) -> list[Path]:
            """
            Return the temp directory as the single source dir.
            """
            return [tmp_path]

        @classmethod
        def get_translation_dir(cls) -> Path:
            """
            Return the temp translations directory.
            """
            return translations_dir

    return TempModule


def test_discover_locales(tmp_path: Path):
    """
    Locales are discovered from JSON file stems.
    """
    module = build_module(tmp_path)
    assert module.discover_locales() == ["es", "fr"]


def test_discover_locales_empty(tmp_path: Path):
    """
    A module with no translation dir discovers no locales.
    """

    class Empty(BaseModuleTranslation):
        """
        Module pointing at a non-existent translations dir.
        """

        @classmethod
        def get_source_dirs(cls) -> list[Path]:
            """
            Return the temp dir.
            """
            return [tmp_path]

        @classmethod
        def get_translation_dir(cls) -> Path:
            """
            Return a non-existent translations dir.
            """
            return tmp_path / "nope"

    assert Empty.discover_locales() == []


def test_has_suffix_matches_the_whole_file_name():
    """
    Suffixes are matched against the name, so compound ones work.
    """
    assert has_suffix(Path("page.html"), DEFAULT_TEMPLATE_SUFFIXES)
    assert has_suffix(Path("page.jinja"), DEFAULT_TEMPLATE_SUFFIXES)
    # pathlib only reports the last one of these, which is why the name is used.
    assert Path("page.html.j2").suffix == ".j2"
    assert has_suffix(Path("page.html.j2"), DEFAULT_TEMPLATE_SUFFIXES)
    assert has_suffix(Path("page.j2.html"), DEFAULT_TEMPLATE_SUFFIXES)
    assert has_suffix(Path("PAGE.HTML"), DEFAULT_TEMPLATE_SUFFIXES)
    assert not has_suffix(Path("notes.txt"), DEFAULT_TEMPLATE_SUFFIXES)
    assert not has_suffix(Path("page.html.j2"), ())


def test_register_translation_loads_all_locales(tmp_path: Path):
    """
    register_translation loads every non-builtin locale from the module.
    """
    module = build_module(tmp_path)
    manager = TranslationManager(builtin_locale="en")
    manager.register_translation(module)
    assert manager.translate("Yes", locale="es") == "Sí"
    assert manager.translate("Yes", locale="fr") == "Oui"
    assert manager.supported_locales() == {Locale("en"), Locale("es"), Locale("fr")}


def test_register_translation_skips_builtin(tmp_path: Path):
    """
    A locale equal to the built-in locale is skipped (no file needed).
    """
    dump_translation_file([TranslationEntry(key="Yes", value="Yes")], tmp_path / "translations" / "en.json")
    module = build_module(tmp_path)
    manager = TranslationManager(builtin_locale="en")
    manager.register_translation(module)
    # en is built-in, so it resolves verbatim regardless of the file content.
    assert manager.translate("Yes", locale="en") == "Yes"
