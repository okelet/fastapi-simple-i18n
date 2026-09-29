"""
Writing side of the web UI: mutating and persisting locale files.

The UI edits the very files the library reads, so every write goes through the
same models and the same :func:`~fastapi_simple_i18n.models.dump_translation_file`
serializer the extraction script uses. There is no second format and no
import/export step.

Two properties are deliberate:

* **Writes are atomic.** The new content is written to a temporary file in the
  same directory, flushed, and then moved over the target with
  :func:`os.replace`, which is atomic on POSIX and Windows. A reader (or a
  crash) therefore sees either the old file or the new one, never a truncated
  JSON document.
* **Order and shape are preserved.** An edit rewrites only the fields it
  changes and keeps the entry in place, and the serializer omits ``variant`` and
  ``draft`` when unset, exactly as the extraction script writes them. Re-saving
  an untouched file is a no-op on disk.
"""

import json
import logging
import os
import tempfile
from pathlib import Path

from ..models import TranslationEntry, TranslationFile, TranslationFormatError
from .catalog import locale_path

logger = logging.getLogger(__name__)


class EntryWriteError(ValueError):
    """
    Raised when a write is rejected before touching the file.

    Carries the message the edit form shows inline, so the user gets a reason
    rather than a silent no-op.
    """


def _identity(entry: TranslationEntry) -> tuple[str, str]:
    """
    Return the ``(key, variant)`` pair identifying an entry.
    """
    return (entry.key, entry.variant or "")


def load_entries(directory: Path, locale: str) -> list[TranslationEntry]:
    """
    Return the entries of one locale file, in file order.

    Raises:
        UnknownLocaleError: If the locale name cannot address a file.
        EntryWriteError: If the file is missing or cannot be parsed. Editing an
            unreadable file is refused rather than replaced with an empty one,
            which would silently drop every translation it held.
    """
    path = locale_path(directory, locale)
    if not path.is_file():
        raise EntryWriteError("File not found.")
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise EntryWriteError(f"Cannot read file: {exc}") from exc
    try:
        return list(TranslationFile.from_json(raw).translations)
    except TranslationFormatError as exc:
        raise EntryWriteError(f"Cannot parse file: {exc}") from exc


def write_entries(directory: Path, locale: str, entries: list[TranslationEntry]) -> None:
    """
    Persist entries to a locale file atomically.

    The parent directory must already exist; the UI only ever writes into a
    directory it listed files from.

    Args:
        directory: Directory holding the locale files.
        locale: File stem of the locale to write.
        entries: Entries to serialize, in the order they should appear.
    """
    path = locale_path(directory, locale)
    # Serialize to a temporary file next to the target (same filesystem, so
    # os.replace stays atomic), then move it into place. mkstemp avoids the
    # symlink/permission surprises of a predictable name.
    handle, temp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            _dump_to(entries, stream)
            stream.flush()
            # Ask the OS to persist before the rename, so a crash right after it
            # cannot leave the renamed file empty.
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except BaseException:
        # Never leave the scratch file behind on failure or cancellation.
        Path(temp_name).unlink(missing_ok=True)
        raise
    logger.info("Wrote %s entries to %s", len(entries), path)


def _dump_to(entries: list[TranslationEntry], stream) -> None:
    """
    Serialize entries into an already-open text stream.

    Mirrors :func:`~fastapi_simple_i18n.models.dump_translation_file` (two-space
    indent, UTF-8, trailing newline) but writes to a stream so the caller can
    flush and fsync before the rename.
    """
    payload = [entry.to_dict() for entry in entries]
    json.dump({"translations": payload}, stream, ensure_ascii=False, indent=2)
    stream.write("\n")


def _find(entries: list[TranslationEntry], index: int) -> TranslationEntry:
    """
    Return the entry at ``index``, or raise :class:`EntryWriteError`.
    """
    if not 0 <= index < len(entries):
        raise EntryWriteError("Entry not found.")
    return entries[index]


def update_entry(
    directory: Path,
    locale: str,
    index: int,
    value: str,
    variant: str | None,
    draft: bool,
) -> list[TranslationEntry]:
    """
    Apply an edit to one entry and save the file.

    Only the edited fields change: the source ``key`` is immutable from the UI
    (renaming a key would silently orphan every code reference to it), while the
    translation, the variant and the draft flag are all editable.

    Args:
        directory: Directory holding the locale files.
        locale: File stem of the locale to write.
        index: Position of the entry in the file.
        value: New translation.
        variant: New variant, or ``None``/empty to clear it.
        draft: New draft flag.

    Returns:
        The saved entries.

    Raises:
        EntryWriteError: If the entry is gone or the new variant would collide
            with another entry of the same file.
    """
    entries = load_entries(directory, locale)
    target = _find(entries, index)
    # Normalize an empty variant field to None: that is how "no variant" is
    # stored, and comparing the raw field would let "" and None both exist.
    normalized = variant or None
    if any(_identity(entry) == (target.key, normalized or "") and position != index for position, entry in enumerate(entries)):
        raise EntryWriteError(f"Another entry already uses the variant '{normalized}' for this key.")
    entries[index] = TranslationEntry(key=target.key, value=value, variant=normalized, draft=draft)
    write_entries(directory, locale, entries)
    return entries


def create_entry(directory: Path, locale: str, key: str, value: str, variant: str | None, draft: bool) -> list[TranslationEntry]:
    """
    Append a new entry to a locale file and save it.

    Args:
        directory: Directory holding the locale files.
        locale: File stem of the locale to write.
        key: Source string. Must not be blank.
        value: Translation.
        variant: Variant, or ``None``/empty for none.
        draft: Draft flag.

    Returns:
        The saved entries.

    Raises:
        EntryWriteError: If the key is blank or the ``(key, variant)`` pair is
            already present, since the pair is the unique unit of a translation.
    """
    entries = load_entries(directory, locale)
    cleaned_key = key.strip()
    if not cleaned_key:
        raise EntryWriteError("The source string cannot be empty.")
    normalized = variant or None
    if any(_identity(entry) == (cleaned_key, normalized or "") for entry in entries):
        raise EntryWriteError("An entry with this source string and variant already exists.")
    entries.append(TranslationEntry(key=cleaned_key, value=value, variant=normalized, draft=draft))
    write_entries(directory, locale, entries)
    return entries


def delete_entry(directory: Path, locale: str, index: int) -> list[TranslationEntry]:
    """
    Remove one entry from a locale file and save it.

    Args:
        directory: Directory holding the locale files.
        locale: File stem of the locale to write.
        index: Position of the entry in the file.

    Returns:
        The saved entries.

    Raises:
        EntryWriteError: If the entry is gone.
    """
    entries = load_entries(directory, locale)
    _find(entries, index)
    del entries[index]
    write_entries(directory, locale, entries)
    return entries
