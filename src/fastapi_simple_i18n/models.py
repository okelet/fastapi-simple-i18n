"""
Core data models for the translation system.

Defines the on-disk JSON format (a list of translation entries) and the
in-memory ``Translation`` object that holds all entries for a single locale.

The models use plain dataclasses plus manual JSON parsing so the core package
depends only on ``babel`` (no pydantic).
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Keys allowed in a single translation entry object in the JSON file.
_ALLOWED_ENTRY_KEYS = {"key", "value", "variant", "draft"}


# The unique unit of a translation: a key together with its optional variant.
ExtractedKey = tuple[str, str | None]


class TranslationFormatError(ValueError):
    """
    Raised when a translation file does not match the expected format.
    """


@dataclass(slots=True)
class TranslationEntry:
    """
    A single translation entry loaded from a locale file.

    Each entry maps a source ``key`` (the string used in the code, written in
    the built-in language of the application) to a translated ``value`` for a
    specific locale. The optional ``variant`` disambiguates entries that share
    the same key (for example the verb vs. the noun form of "Archive"). The
    ``draft`` flag marks a value as provisional; drafts are still used at
    runtime but can be reviewed and completed later.
    """

    key: str
    value: str
    variant: str | None = None
    draft: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> TranslationEntry:
        """
        Build an entry from a raw JSON object, validating its shape.

        Raises:
            TranslationFormatError: If required fields are missing, fields have
                the wrong type, or unknown fields are present.
        """
        if not isinstance(data, dict):
            raise TranslationFormatError(f"Entry must be an object, got {type(data).__name__}")

        unknown = set(data.keys()) - _ALLOWED_ENTRY_KEYS
        if unknown:
            raise TranslationFormatError(f"Unknown field(s) in entry: {', '.join(sorted(unknown))}")

        key = data.get("key")
        value = data.get("value")
        variant = data.get("variant")
        draft = data.get("draft", False)

        if not isinstance(key, str):
            raise TranslationFormatError("Entry 'key' must be a string")
        if not isinstance(value, str):
            raise TranslationFormatError("Entry 'value' must be a string")
        if variant is not None and not isinstance(variant, str):
            raise TranslationFormatError("Entry 'variant' must be a string or absent")
        if not isinstance(draft, bool):
            raise TranslationFormatError("Entry 'draft' must be a boolean")

        return cls(key=key, value=value, variant=variant, draft=draft)

    def to_dict(self) -> dict[str, object]:
        """
        Serialize the entry to a plain dict, omitting unset optional fields.

        ``variant`` and ``draft`` are omitted when unset to keep files tidy.
        """
        item: dict[str, object] = {"key": self.key, "value": self.value}
        if self.variant is not None:
            item["variant"] = self.variant
        if self.draft:
            item["draft"] = True
        return item


@dataclass(slots=True)
class TranslationFile:
    """
    The on-disk representation of a locale file.

    A locale file contains a single ``translations`` list of entries.
    """

    translations: list[TranslationEntry] = field(default_factory=list)

    @classmethod
    def from_json(cls, raw: str) -> TranslationFile:
        """
        Parse and validate a locale file from a JSON string.

        Raises:
            TranslationFormatError: If the JSON is malformed or does not match
                the expected ``{"translations": [...]}`` shape.
        """
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TranslationFormatError(f"Invalid JSON: {exc}") from exc

        if not isinstance(data, dict):
            raise TranslationFormatError("Top-level value must be an object")

        translations = data.get("translations", [])
        if not isinstance(translations, list):
            raise TranslationFormatError("'translations' must be a list")

        return cls([TranslationEntry.from_dict(item) for item in translations])


def _entry_lookup_key(key: str, variant: str | None) -> tuple[str, str | None]:
    """
    Build the internal lookup tuple used to index entries uniquely.

    The unique unit of a translation is the pair ``(key, variant)``.
    """
    return (key, variant)


class Translation:
    """
    In-memory collection of translations for a single locale.

    Entries are indexed by their ``(key, variant)`` pair so lookups are O(1).
    A ``Translation`` is typically produced by :meth:`from_file` but can also
    be constructed manually (useful for tests or CLI scripts).
    """

    def __init__(self, locale: str, entries: list[TranslationEntry] | None = None) -> None:
        """
        Initialize the translation store for a locale.

        Args:
            locale: The locale code this translation belongs to (e.g. ``"es"``).
            entries: Optional initial list of entries to index.
        """
        self.locale = locale
        self._entries: dict[tuple[str, str | None], TranslationEntry] = {}
        for entry in entries or []:
            self.add(entry)

    def add(self, entry: TranslationEntry) -> None:
        """
        Add or replace an entry in the store.

        Later entries with the same ``(key, variant)`` pair overwrite earlier
        ones.
        """
        self._entries[_entry_lookup_key(entry.key, entry.variant)] = entry

    def get(self, key: str, variant: str | None = None) -> TranslationEntry | None:
        """
        Look up an entry by key and optional variant.

        Returns ``None`` if no matching entry exists.
        """
        return self._entries.get(_entry_lookup_key(key, variant))

    def entries(self) -> list[TranslationEntry]:
        """
        Return all entries as a list.
        """
        return list(self._entries.values())

    def __len__(self) -> int:
        """
        Return the number of entries stored.
        """
        return len(self._entries)

    @classmethod
    def from_file(cls, locale: str, path: Path) -> Translation:
        """
        Build a ``Translation`` by loading and validating a locale JSON file.

        Returns an empty translation (with a logged warning) if the file does
        not exist or cannot be parsed.

        Args:
            locale: The locale code the file corresponds to.
            path: Path to the locale JSON file.
        """
        if not path.is_file():
            logger.warning("Translation file not found: %s", path)
            return cls(locale)
        try:
            raw = path.read_text(encoding="utf-8")
            data = TranslationFile.from_json(raw)
        except (OSError, TranslationFormatError) as exc:
            logger.warning("Failed to load translation file %s: %s", path, exc)
            return cls(locale)
        return cls(locale, data.translations)

    @classmethod
    def from_entries(cls, locale: str, entries: list[TranslationEntry]) -> Translation:
        """
        Build a ``Translation`` directly from a list of entries.
        """
        return cls(locale, entries)


def dump_translation_file(entries: list[TranslationEntry], path: Path) -> None:
    """
    Write a list of entries to a locale JSON file.

    Entries are serialized as a ``{"translations": [...]}`` object. Fields with
    default values (``variant``/``draft``) are omitted when unset to keep files
    tidy. The output is UTF-8, non-ASCII preserved, indented with two spaces.

    Args:
        entries: The entries to serialize.
        path: Destination file path (parent directories are created).
    """
    payload = [entry.to_dict() for entry in entries]

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump({"translations": payload}, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
