"""
Read-only view over the translation files of a directory.

The UI deliberately does not keep its own copy of a catalog: every request
re-reads the files from disk, so a translation committed with git, edited in
another editor or refreshed by the extraction script is visible immediately and
there is no cache to invalidate.

Everything here is pure with respect to the request: functions take the
directory and return plain data, which keeps the filtering and the
placeholder checks trivially testable.
"""

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..locale import resolve_locale
from ..models import TranslationEntry, TranslationFile, TranslationFormatError

logger = logging.getLogger(__name__)

# Locales are file stems, so a safe one may only contain word characters and
# dashes. Refusing everything else keeps "../" and friends out of the path
# built by :func:`locale_path`.
LOCALE_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

# Placeholders understood by the runtime: ``str.format`` fields (``{name}``,
# possibly with a conversion or a format spec) and printf-style ``%(name)s``.
FORMAT_FIELD_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)(?::[^{}]*)?\}")
PERCENT_FIELD_PATTERN = re.compile(r"%\(([^)]+)\)")


class UnknownLocaleError(ValueError):
    """
    Raised when a locale name cannot address a file inside the directory.
    """


def locale_path(directory: Path, locale: str) -> Path:
    """
    Return the path of the file backing ``locale``.

    ``LOCALE_PATTERN`` is the guarantee: it admits only word characters and
    dashes, so the name can hold neither a separator nor a dot and the joined
    path always stays directly inside ``directory``.

    Args:
        directory: Directory holding the locale files.
        locale: File stem of the locale, such as ``"es"`` or ``"pt-BR"``.

    Raises:
        UnknownLocaleError: If the name is empty or contains anything but word
            characters and dashes.
    """
    if not LOCALE_PATTERN.match(locale):
        raise UnknownLocaleError(locale)
    return directory / f"{locale}.json"


def placeholder_names(text: str) -> set[str]:
    """
    Return the placeholder names used by a string.

    Recognises both syntaxes the library formats with: ``{name}`` (``str.format``,
    used by the helpers) and ``%(name)s`` (``gettext`` style, used inside
    ``{% trans %}`` blocks). A duplicated name counts once.
    """
    return set(FORMAT_FIELD_PATTERN.findall(text)) | set(PERCENT_FIELD_PATTERN.findall(text))


def placeholder_issues(key: str, value: str) -> list[str]:
    """
    Return the placeholder mismatches between the source string and its translation.

    An empty list means the translation carries every placeholder the source
    declares (and declares none of its own). A missing placeholder would raise
    ``KeyError``/``IndexError`` at render time and an extra one would render as
    a literal, so both are worth flagging while translating. A draft with an
    empty value reports nothing: it has nothing to compare yet.
    """
    if not value:
        return []
    source = placeholder_names(key)
    translated = placeholder_names(value)
    issues = [f"missing {name}" for name in sorted(source - translated)]
    issues += [f"unexpected {name}" for name in sorted(translated - source)]
    return issues


def locale_display_name(locale: str) -> str:
    """
    Return the name of a locale written in that locale (``"es"`` -> ``"español"``).

    Resolved through the library's own :func:`~fastapi_simple_i18n.locale.resolve_locale`,
    so a file named after any spelling of a locale (``pt_BR``, ``pt-BR``) gets a
    display name. The raw name is returned when it is not a locale at all, since
    a file stem is not required to be a well-formed language tag.
    """
    try:
        parsed = resolve_locale(locale)
    except ValueError:
        return locale
    return parsed.get_display_name(parsed) or locale


def flag_emoji(locale: str) -> str:
    """
    Return the flag emoji for the region of a locale, or an empty string.

    Regional-indicator symbols encode a country as two code points; locales
    without a territory (or with a numeric one) have no flag to show, and so
    does a name that is not a locale at all.
    """
    try:
        territory = resolve_locale(locale).territory or ""
    except ValueError:
        return ""
    if len(territory) != 2 or not territory.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(char) - ord("A")) for char in territory.upper())


@dataclass(frozen=True, slots=True)
class LocaleSummary:
    """
    One row of the locales index.

    Attributes:
        locale: File stem, used in URLs.
        display_name: Name of the locale in that locale.
        flag: Flag emoji derived from the territory, possibly empty.
        file_name: Name of the backing file.
        size: File size in bytes.
        modified: Last modification time, or ``None`` when unavailable.
        entry_count: Number of entries in the file.
        draft_count: Number of entries flagged as drafts.
        empty_count: Number of entries whose translation is still blank.
        error: Why the file could not be read, or ``None`` when it parsed.
    """

    locale: str
    display_name: str
    flag: str
    file_name: str
    size: int
    modified: datetime | None
    entry_count: int
    draft_count: int
    empty_count: int
    error: str | None = None

    @property
    def is_readable(self) -> bool:
        """
        Whether the file parsed and its entries can be listed.
        """
        return self.error is None


@dataclass(frozen=True, slots=True)
class EntryRow:
    """
    A single entry as the table renders it, with its position in the file.

    ``index`` is what the edit and delete endpoints address: the
    ``(key, variant)`` pair is the stable identity of a translation, but it is
    awkward to carry through a URL, and it also tells the row where it sits in
    the file so a write can put the entry back where it was.
    """

    index: int
    key: str
    value: str
    variant: str | None
    draft: bool

    @property
    def is_empty(self) -> bool:
        """
        Whether the translation is still blank (a fresh extraction stub).
        """
        return not self.value

    @property
    def placeholders(self) -> list[str]:
        """
        Placeholder mismatches between the source string and the translation.
        """
        return placeholder_issues(self.key, self.value)


@dataclass(frozen=True, slots=True)
class LocaleCatalog:
    """
    A locale file and its parsed entries.

    Attributes:
        locale: File stem.
        display_name: Name of the locale in that locale.
        flag: Flag emoji derived from the territory, possibly empty.
        file_name: Name of the backing file.
        rows: Entries in file order, empty when ``error`` is set.
        error: Why the file could not be read, or ``None`` when it parsed.
    """

    locale: str
    display_name: str
    flag: str
    file_name: str
    rows: tuple[EntryRow, ...] = ()
    error: str | None = None

    @property
    def entry_count(self) -> int:
        """
        Total number of entries in the file.
        """
        return len(self.rows)

    @property
    def draft_count(self) -> int:
        """
        Number of entries flagged as drafts.
        """
        return sum(1 for row in self.rows if row.draft)

    @property
    def variant_count(self) -> int:
        """
        Number of entries that carry a variant.
        """
        return sum(1 for row in self.rows if row.variant)

    @property
    def is_readable(self) -> bool:
        """
        Whether the file parsed and its entries can be listed.
        """
        return self.error is None


@dataclass(frozen=True, slots=True)
class EntriesPage:
    """
    One page of filtered entries plus the counters the table footer shows.

    Attributes:
        rows: Entries on this page.
        total: Number of entries matching the filters across the whole file.
        page: 1-based page number, clamped into range.
        page_size: Number of entries per page.
    """

    rows: tuple[EntryRow, ...] = ()
    total: int = 0
    page: int = 1
    page_size: int = 50
    # EntryFilter is defined below; the lambda defers the lookup to call time.
    filters: EntryFilter = field(default_factory=lambda: EntryFilter())  # noqa: PLW0108  # pylint: disable=unnecessary-lambda

    @property
    def total_pages(self) -> int:
        """
        Number of pages, at least one even when nothing matched.
        """
        return max(1, -(-self.total // self.page_size))

    @property
    def has_previous(self) -> bool:
        """
        Whether a previous page exists.
        """
        return self.page > 1

    @property
    def has_next(self) -> bool:
        """
        Whether a next page exists.
        """
        return self.page < self.total_pages

    @property
    def range_start(self) -> int:
        """
        1-based index of the first row shown, or 0 when the page is empty.
        """
        return 0 if not self.rows else (self.page - 1) * self.page_size + 1

    @property
    def range_end(self) -> int:
        """
        1-based index of the last row shown.
        """
        return 0 if not self.rows else (self.page - 1) * self.page_size + len(self.rows)


@dataclass(frozen=True, slots=True)
class EntryFilter:
    """
    The filters the strings table offers, as submitted by the search form.

    Attributes:
        text: Free text matched against the source string and the translation.
        variants: Selected variant options, where ``""`` means "no variant". An
            empty selection means every variant is shown.
        draft: Tri-state draft filter: ``""`` (any), ``"draft"`` or ``"final"``.
    """

    text: str = ""
    variants: tuple[str, ...] = ()
    draft: str = ""

    @property
    def is_empty(self) -> bool:
        """
        Whether no filter at all is active.
        """
        return not self.text and not self.variants and not self.draft


def fold(text: str) -> str:
    """
    Fold a string for accent- and case-insensitive matching.

    Diacritics are stripped through NFKD decomposition (``"café"`` -> ``"cafe"``)
    so a translator can type the Spanish word without accents, and every run of
    non-alphanumeric characters becomes a single space so punctuation never
    blocks a match.
    """
    decomposed = unicodedata.normalize("NFKD", text.lower())
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join("".join(char if char.isalnum() else " " for char in stripped).split())


def matches_filter(row: EntryRow, tokens: list[str], entry_filter: EntryFilter) -> bool:
    """
    Return whether one row survives the active filters.

    Every token of the free-text query must appear somewhere in the row's
    source string or translation, so a query can span both. The selected
    variants are matched against ``row.variant or ""``, which is what makes the
    "no variant" option work without a special case.
    """
    if entry_filter.variants and (row.variant or "") not in entry_filter.variants:
        return False
    if entry_filter.draft == "draft" and not row.draft:
        return False
    if entry_filter.draft == "final" and row.draft:
        return False
    if not tokens:
        return True
    haystack = fold(f"{row.key} {row.value}")
    return all(token in haystack for token in tokens)


def filter_rows(rows: list[EntryRow], entry_filter: EntryFilter) -> list[EntryRow]:
    """
    Return the rows matching ``entry_filter``, in file order.
    """
    tokens = fold(entry_filter.text).split()
    return [row for row in rows if matches_filter(row, tokens, entry_filter)]


def paginate(rows: list[EntryRow], page: int, page_size: int, entry_filter: EntryFilter) -> EntriesPage:
    """
    Return one page of already filtered rows.

    The page number is clamped into range, so a stale ``page`` query parameter
    (a filter change, a trimmed file) lands on the last page instead of
    returning nothing.
    """
    size = max(1, page_size)
    total_pages = max(1, -(-len(rows) // size))
    current = min(max(1, page), total_pages)
    start = (current - 1) * size
    return EntriesPage(rows=tuple(rows[start : start + size]), total=len(rows), page=current, page_size=size, filters=entry_filter)


def _read_catalog(path: Path, locale: str) -> LocaleCatalog:
    """
    Read and parse one locale file, turning any failure into an error message.

    A file that cannot be parsed must not take the page down: the caller shows
    the message and offers the raw file, which is what a translator needs to fix
    it.
    """
    display_name = locale_display_name(locale)
    flag = flag_emoji(locale)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return LocaleCatalog(locale, display_name, flag, path.name, error=f"Cannot read file: {exc}")

    try:
        entries = TranslationFile.from_json(raw).translations
    except TranslationFormatError as exc:
        logger.warning("Could not parse translation file %s: %s", path, exc)
        return LocaleCatalog(locale, display_name, flag, path.name, error=str(exc))

    rows = tuple(EntryRow(index=index, key=entry.key, value=entry.value, variant=entry.variant, draft=entry.draft) for index, entry in enumerate(entries))
    return LocaleCatalog(locale, display_name, flag, path.name, rows=rows)


def load_catalog(directory: Path, locale: str) -> LocaleCatalog:
    """
    Return the parsed contents of one locale file.

    Raises:
        UnknownLocaleError: If the locale name cannot address a file.
    """
    path = locale_path(directory, locale)
    if not path.is_file():
        return LocaleCatalog(locale, locale_display_name(locale), flag_emoji(locale), path.name, error="File not found.")
    return _read_catalog(path, locale)


def list_locales(directory: Path) -> list[LocaleSummary]:
    """
    Return one summary per locale file in ``directory``, sorted by locale.

    Non-JSON files in the directory are ignored: they are not translations and
    the UI has nothing to show for them.
    """
    if not directory.is_dir():
        return []
    summaries: list[LocaleSummary] = []
    for path in sorted(directory.glob("*.json")):
        catalog = _read_catalog(path, path.stem)
        try:
            stat = path.stat()
            size, modified = stat.st_size, datetime.fromtimestamp(stat.st_mtime)
        except OSError:  # pragma: no cover - the file vanished mid-listing
            size, modified = 0, None
        summaries.append(
            LocaleSummary(
                locale=catalog.locale,
                display_name=catalog.display_name,
                flag=catalog.flag,
                file_name=catalog.file_name,
                size=size,
                modified=modified,
                entry_count=catalog.entry_count,
                draft_count=catalog.draft_count,
                empty_count=sum(1 for row in catalog.rows if row.is_empty),
                error=catalog.error,
            )
        )
    return summaries


def collect_variants(directory: Path) -> list[str]:
    """
    Return every distinct variant found in any locale file, sorted.

    The multiselect is populated from the whole directory rather than from the
    locale being viewed, so the same option list applies to every file and the
    filter stays comparable across locales.
    """
    if not directory.is_dir():
        return []
    variants: set[str] = set()
    for path in sorted(directory.glob("*.json")):
        try:
            entries = TranslationFile.from_json(path.read_text(encoding="utf-8")).translations
        except (OSError, TranslationFormatError):
            continue
        variants.update(entry.variant for entry in entries if entry.variant)
    return sorted(variants, key=str.casefold)


def read_raw(directory: Path, locale: str) -> str:
    """
    Return the verbatim contents of a locale file, for the "view raw" fallback.

    Raises:
        UnknownLocaleError: If the locale name cannot address a file.
        OSError: If the file cannot be read.
    """
    return locale_path(directory, locale).read_text(encoding="utf-8")


def build_rows(entries: list[TranslationEntry]) -> list[EntryRow]:
    """
    Wrap parsed entries into table rows, preserving their file order.

    The index is the position in the list, which is what the write side uses to
    put an edited entry back exactly where it was.
    """
    return [EntryRow(index=index, key=entry.key, value=entry.value, variant=entry.variant, draft=entry.draft) for index, entry in enumerate(entries)]


def pretty_json(text: str) -> str:
    """
    Return ``text`` re-indented as JSON, falling back to the input when it does not parse.
    """
    try:
        return json.dumps(json.loads(text), ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, TypeError):
        return text
