"""
Tests for the core models: TranslationEntry, Translation, file I/O.
"""

from pathlib import Path

import pytest
from babel.core import Locale

from fastapi_simple_i18n.models import Translation, TranslationEntry, TranslationFile, TranslationFormatError, dump_translation_file


def test_entry_defaults():
    """
    A minimal entry has no variant and is not a draft.
    """
    entry = TranslationEntry(key="Yes", value="Sí")
    assert entry.variant is None
    assert entry.draft is False


def test_translation_lookup_by_key_and_variant():
    """
    Entries are indexed uniquely by the (key, variant) pair.
    """
    translation = Translation(
        "es",
        [
            TranslationEntry(key="Archive", value="Archivar", variant="verb"),
            TranslationEntry(key="Archive", value="Archivo", variant="noun"),
        ],
    )
    assert translation.get("Archive", "verb").value == "Archivar"
    assert translation.get("Archive", "noun").value == "Archivo"
    assert translation.get("Archive") is None
    assert len(translation) == 2


def test_translation_add_overwrites_same_pair():
    """
    Adding an entry with an existing (key, variant) pair overwrites it.
    """
    translation = Translation("es", [TranslationEntry(key="Yes", value="Sí")])
    translation.add(TranslationEntry(key="Yes", value="Correcto"))
    assert translation.get("Yes").value == "Correcto"
    assert len(translation) == 1


def test_from_file_roundtrip(tmp_path: Path):
    """
    Entries written with dump_translation_file load back identically.
    """
    entries = [
        TranslationEntry(key="Yes", value="Sí"),
        TranslationEntry(key="Archive", value="Archivo", variant="noun"),
        TranslationEntry(key="My items", value="Mis elementos", draft=True),
    ]
    path = tmp_path / "es.json"
    dump_translation_file(entries, path)

    loaded = Translation.from_file("es", path)
    assert loaded.get("Yes").value == "Sí"
    assert loaded.get("Archive", "noun").value == "Archivo"
    assert loaded.get("My items").draft is True


def test_dump_omits_default_fields(tmp_path: Path):
    """
    The variant and draft fields are omitted from the JSON when unset.
    """
    path = tmp_path / "es.json"
    dump_translation_file([TranslationEntry(key="Yes", value="Sí")], path)
    content = path.read_text(encoding="utf-8")
    assert '"variant"' not in content
    assert '"draft"' not in content


def test_from_file_missing_returns_empty(tmp_path: Path):
    """
    Loading a non-existent file returns an empty translation, not an error.
    """
    loaded = Translation.from_file("es", tmp_path / "does_not_exist.json")
    assert len(loaded) == 0


def test_from_file_invalid_json_returns_empty(tmp_path: Path):
    """
    Loading malformed JSON returns an empty translation, not an error.
    """
    path = tmp_path / "es.json"
    path.write_text("{ not valid json", encoding="utf-8")
    loaded = Translation.from_file("es", path)
    assert len(loaded) == 0


def test_translation_file_rejects_unknown_fields():
    """
    Unknown fields in an entry raise a validation error.
    """
    with pytest.raises(TranslationFormatError):
        TranslationFile.from_json('{"translations": [{"key": "Yes", "value": "Sí", "bogus": 1}]}')


def test_translation_file_rejects_wrong_types():
    """
    Wrong field types raise a validation error.
    """
    with pytest.raises(TranslationFormatError):
        TranslationFile.from_json('{"translations": [{"key": "Yes", "value": 123}]}')


def test_translation_file_rejects_non_object_top_level():
    """
    A non-object top-level value raises a validation error.
    """
    with pytest.raises(TranslationFormatError):
        TranslationFile.from_json("[]")


# --- Locale handling ---


def test_translation_locale_is_a_locale_object():
    """
    The locale is stored resolved, so it is usable as a key straight away.
    """
    translation = Translation("ES-es", [TranslationEntry(key="Yes", value="Sí")])
    assert isinstance(translation.locale, Locale)
    assert translation.locale == Locale("es", territory="ES")


@pytest.mark.parametrize(
    "factory",
    [
        pytest.param(Translation, id="Translation"),
        pytest.param(lambda locale: Translation.from_entries(locale, []), id="from_entries"),
        pytest.param(lambda locale: Translation.from_file(locale, Path("does_not_exist.json")), id="from_file"),
    ],
)
def test_translation_validates_its_locale(factory):
    """
    A Translation is never built for a locale that does not exist.
    """
    with pytest.raises(ValueError, match="Invalid locale 'xx_YY'"):
        factory("xx_YY")


def test_translation_accepts_a_locale_object():
    """
    An already resolved locale is accepted as-is.
    """
    locale = Locale("pt", territory="BR")
    assert Translation(locale).locale is locale
