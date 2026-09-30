"""
Tests for the translation web UI.

The suite exercises the pure helpers (:mod:`fastapi_simple_i18n.web.catalog`,
:mod:`fastapi_simple_i18n.web.storage`) directly and the FastAPI app through
an ``httpx.AsyncClient`` against the in-memory ASGI transport, so it runs
without a network socket or the ``uvicorn`` server.
"""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fastapi_simple_i18n.models import TranslationEntry, dump_translation_file
from fastapi_simple_i18n.web.app import create_app
from fastapi_simple_i18n.web.catalog import (
    EntriesPage,
    EntryFilter,
    EntryRow,
    LocaleCatalog,
    UnknownLocaleError,
    collect_variants,
    filter_rows,
    flag_emoji,
    fold,
    list_locales,
    load_catalog,
    locale_display_name,
    locale_path,
    matches_filter,
    paginate,
    placeholder_issues,
    placeholder_names,
)
from fastapi_simple_i18n.web.config import Settings
from fastapi_simple_i18n.web.storage import (
    EntryWriteError,
    create_entry,
    delete_entry,
    load_entries,
    update_entry,
)

# --- fixtures ---------------------------------------------------------------


@pytest.fixture(name="translations_dir")
def translations_dir_fixture(tmp_path: Path) -> Path:
    """
    A directory with two locales, one of which has variants and a draft.
    """
    es = [
        TranslationEntry(key="Archive", value="Archivo", variant="noun"),
        TranslationEntry(key="Archive", value="Archivar", variant="verb"),
        TranslationEntry(key="Hello, {name}!", value="¡Hola, {name}!"),
        TranslationEntry(key="Signed in", value="Sesión iniciada"),
        TranslationEntry(key="My items", value="", draft=True),
    ]
    fr = [
        TranslationEntry(key="Archive", value="Archive", variant="noun"),
        TranslationEntry(key="Hello, {name}!", value="Bonjour {name}!"),
    ]
    dump_translation_file(es, tmp_path / "es.json")
    dump_translation_file(fr, tmp_path / "fr.json")
    return tmp_path


@pytest.fixture(name="app")
def app_fixture(translations_dir: Path) -> FastAPI:
    """
    A FastAPI app pointing at the test translations directory.
    """
    return create_app(Settings(translations_dir=translations_dir, page_size=10))


@pytest.fixture(name="client")
def client_fixture(app: FastAPI) -> TestClient:
    """
    A synchronous test client wrapping the FastAPI app.
    """
    return TestClient(app, raise_server_exceptions=True)


# --- pure helpers: catalog --------------------------------------------------


def test_locale_path_rejects_traversal() -> None:
    """
    A locale name with a path separator or dot is refused before the path is joined.
    """
    with pytest.raises(UnknownLocaleError):
        locale_path(Path("."), "..")
    with pytest.raises(UnknownLocaleError):
        locale_path(Path("."), "es/../etc")
    with pytest.raises(UnknownLocaleError):
        locale_path(Path("."), "")
    with pytest.raises(UnknownLocaleError):
        locale_path(Path("."), "es.json")


def test_locale_display_name_and_flag() -> None:
    """
    Babel parses well-formed locales; flag derives from the territory.
    """
    assert locale_display_name("es") == "español"
    assert locale_display_name("pt-BR") == "português (Brasil)"
    assert locale_display_name("not_a_locale") == "not_a_locale"
    assert flag_emoji("es") == ""
    assert flag_emoji("pt-BR") == "🇧🇷"
    assert flag_emoji("nonsense") == ""


def test_locale_display_name_accepts_every_spelling() -> None:
    """
    A file named after any spelling of a locale is still a locale.

    Locale files are named after locales, and the library accepts ``_`` and
    ``-`` interchangeably, so the UI must too: an ``es_ES.json`` file gets the
    same display name (and flag) as an ``es-ES.json`` one.
    """
    assert locale_display_name("es_ES") == locale_display_name("es-ES") == locale_display_name("ES-es")
    assert locale_display_name("zh_Hans_CN") == locale_display_name("zh-hans-cn")
    assert flag_emoji("es_ES") == flag_emoji("es-ES") == "🇪🇸"
    assert flag_emoji("zh_Hans_CN") == "🇨🇳"
    assert flag_emoji("not_a_locale") == ""


def test_placeholder_names_recognises_both_syntaxes() -> None:
    """
    str.format fields and printf-style fields are both captured.
    """
    assert placeholder_names("Hi {name}, you have {count:02d} items") == {"name", "count"}
    assert placeholder_names("Il y a %(item_count)s articles") == {"item_count"}
    assert placeholder_names("Nothing") == set()


def test_placeholder_issues_reports_missing_and_extra() -> None:
    """
    Missing placeholders would crash at render time; extra ones would print literally.
    """
    issues = placeholder_issues("Hi {name}, you have {count}", "Bonjour {name}")
    assert "missing count" in issues
    assert issues == sorted(issues)  # reported in a stable order


def test_placeholder_issues_skips_empty_translations() -> None:
    """
    An empty translation reports nothing — there is nothing to compare yet.
    """
    assert placeholder_issues("Hello {name}", "") == []


def test_fold_strips_accents_and_punctuation() -> None:
    """
    Folding is accent- and case-insensitive and collapses punctuation.
    """
    assert fold("Café") == "cafe"
    assert fold("AMAZON*PAYMENTS") == "amazon payments"
    assert fold("  one   two  ") == "one two"


def test_list_locales_returns_summary_with_counts(translations_dir: Path) -> None:
    """
    Every locale in the directory shows up with its entry, draft and empty counts.
    """
    summaries = list_locales(translations_dir)
    assert [s.locale for s in summaries] == ["es", "fr"]
    es = next(s for s in summaries if s.locale == "es")
    assert es.entry_count == 5
    assert es.draft_count == 1
    assert es.empty_count == 1
    assert es.error is None
    assert es.size > 0
    assert es.modified is not None


def test_list_locales_surfaces_parse_errors(tmp_path: Path) -> None:
    """
    A malformed file produces a row with an error message instead of raising.
    """
    (tmp_path / "bad.json").write_text("not valid json", encoding="utf-8")
    summaries = list_locales(tmp_path)
    assert len(summaries) == 1
    assert summaries[0].error is not None


def test_load_catalog_returns_rows_in_file_order(translations_dir: Path) -> None:
    """
    The catalog preserves file order — important for index-based writes.
    """
    catalog = load_catalog(translations_dir, "es")
    assert isinstance(catalog, LocaleCatalog)
    assert catalog.is_readable
    assert [r.key for r in catalog.rows] == ["Archive", "Archive", "Hello, {name}!", "Signed in", "My items"]
    assert catalog.rows[0].variant == "noun"
    assert catalog.rows[1].variant == "verb"


def test_load_catalog_marks_missing_file() -> None:
    """
    A missing locale file is rendered as a readable=false catalog.
    """
    catalog = load_catalog(Path("/tmp/does-not-exist"), "es")
    assert catalog.is_readable is False
    assert catalog.error is not None


def test_collect_variants_unions_across_files(translations_dir: Path) -> None:
    """
    Variant values from every locale file are merged.
    """
    assert collect_variants(translations_dir) == ["noun", "verb"]


def test_filter_rows_matches_text_in_key_or_value() -> None:
    """
    Free-text search hits both the source and the translation.
    """
    rows = [
        EntryRow(index=0, key="Hello", value="Bonjour", variant=None, draft=False),
        EntryRow(index=1, key="Search", value="Recherche", variant=None, draft=False),
        EntryRow(index=2, key="Archive", value="Archivar", variant="verb", draft=False),
    ]
    keep = filter_rows(rows, EntryFilter(text="arch"))
    assert [r.index for r in keep] == [1, 2]  # matches "Search" (folded) and "Archivar"


def test_filter_rows_respects_variants_and_draft() -> None:
    """
    The variant multiselect and the draft tri-state work in combination.
    """
    rows = [
        EntryRow(index=0, key="Archive", value="Archivo", variant="noun", draft=False),
        EntryRow(index=1, key="Archive", value="Archivar", variant="verb", draft=True),
        EntryRow(index=2, key="Hello", value="Hola", variant=None, draft=False),
    ]
    assert [r.index for r in filter_rows(rows, EntryFilter(variants=("verb",)))] == [1]
    assert [r.index for r in filter_rows(rows, EntryFilter(draft="draft"))] == [1]
    assert [r.index for r in filter_rows(rows, EntryFilter(variants=("", "noun")))] == [0, 2]


def test_paginate_clamps_page_and_reports_range() -> None:
    """
    A page outside the available range is clamped; the range counters never go negative.
    """
    rows = [EntryRow(index=i, key=f"K{i}", value="", variant=None, draft=False) for i in range(25)]
    page = paginate(rows, page=99, page_size=10, entry_filter=EntryFilter())
    assert isinstance(page, EntriesPage)
    assert page.page == 3
    assert page.total == 25
    assert page.total_pages == 3
    assert page.range_start == 21
    assert page.range_end == 25

    empty_page = paginate([], page=1, page_size=10, entry_filter=EntryFilter())
    assert empty_page.range_start == 0
    assert empty_page.range_end == 0


# --- pure helpers: storage ---------------------------------------------------


def test_update_entry_writes_atomically_and_preserves_order(translations_dir: Path) -> None:
    """
    Editing one entry keeps every other entry at its original position and atomically replaces the file.
    """
    entries_before = load_entries(translations_dir, "es")
    update_entry(translations_dir, "es", index=3, value="Iniciar sesión", variant=None, draft=False)
    entries_after = load_entries(translations_dir, "es")
    # The edited entry moved out of the draft flag; the others stayed put.
    assert entries_after[0] == entries_before[0]
    assert entries_after[1] == entries_before[1]
    assert entries_after[2] == entries_before[2]
    assert entries_after[3] == TranslationEntry(key="Signed in", value="Iniciar sesión")
    assert entries_after[4] == entries_before[4]


def test_update_entry_rejects_variant_collision(translations_dir: Path) -> None:
    """
    Editing the variant so it collides with another entry's variant raises EntryWriteError.
    """
    with pytest.raises(EntryWriteError, match="variant"):
        update_entry(translations_dir, "es", index=0, value="x", variant="verb", draft=False)


def test_update_entry_rejects_unknown_index(translations_dir: Path) -> None:
    """
    An out-of-range index is a validation failure, not an out-of-bounds crash.
    """
    with pytest.raises(EntryWriteError):
        update_entry(translations_dir, "es", index=99, value="x", variant=None, draft=False)


def test_create_entry_appends_and_rejects_duplicates(translations_dir: Path) -> None:
    """
    New entries land at the end; re-using the (key, variant) pair is refused.
    """
    before = len(load_entries(translations_dir, "es"))
    create_entry(translations_dir, "es", key="New", value="Nuevo", variant=None, draft=False)
    after = load_entries(translations_dir, "es")
    assert len(after) == before + 1
    assert after[-1] == TranslationEntry(key="New", value="Nuevo")

    with pytest.raises(EntryWriteError, match="already exists"):
        create_entry(translations_dir, "es", key="Archive", value="x", variant="verb", draft=False)


def test_create_entry_rejects_blank_key(translations_dir: Path) -> None:
    """
    An empty source string is refused so an editor cannot silently insert noise.
    """
    with pytest.raises(EntryWriteError, match="empty"):
        create_entry(translations_dir, "es", key="   ", value="x", variant=None, draft=False)


def test_delete_entry_removes_one_row(translations_dir: Path) -> None:
    """
    Deleting an entry removes exactly that row.
    """
    before = [e.key for e in load_entries(translations_dir, "es")]
    delete_entry(translations_dir, "es", index=4)
    after = [e.key for e in load_entries(translations_dir, "es")]
    assert after == before[:4]


def test_storage_refuses_to_load_unreadable_file(tmp_path: Path) -> None:
    """
    Storage cannot overwrite a file it cannot read, so a stray network-blip does not destroy work.
    """
    (tmp_path / "broken.json").write_text("not valid json", encoding="utf-8")
    with pytest.raises(EntryWriteError, match="parse"):
        load_entries(tmp_path, "broken")


# --- the FastAPI app --------------------------------------------------------


def test_index_lists_locales(client: TestClient) -> None:
    """
    The locales index lists every locale in the directory.
    """
    response = client.get("/")
    assert response.status_code == 200
    body = response.text
    assert "es" in body and "fr" in body
    assert "español" in body
    assert "français" in body


def test_index_shows_missing_directory(tmp_path: Path) -> None:
    """
    When the directory is missing, the page explains what to do instead of erroring.
    """
    app = create_app(Settings(translations_dir=tmp_path / "missing"))
    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert "does not exist" in response.text


def test_locale_strings_page_renders_initial_table(client: TestClient) -> None:
    """
    The strings page renders the page shell with the full table.
    """
    response = client.get("/locales/es")
    assert response.status_code == 200
    assert "Archive" in response.text
    assert "Mis artículos" not in response.text  # empty value, rendered as "untranslated"


def test_strings_fragment_returns_just_the_partial(client: TestClient) -> None:
    """
    The search form's ``hx-get`` target returns the results fragment only.
    """
    response = client.get("/locales/es/strings", params={"q": "arch"})
    assert response.status_code == 200
    assert "<table" in response.text
    assert "<html" not in response.text  # not the full page shell


def test_locale_strings_filters_work(client: TestClient) -> None:
    """
    Search, variant and draft filters all reach the server.
    """
    response = client.get("/locales/es/strings", params={"variant": "noun"})
    assert response.status_code == 200
    assert "Archive" in response.text  # variant "noun" present
    assert "Archivar" not in response.text  # variant "verb" filtered out


def test_strings_fragment_search_matches_filtres(client: TestClient) -> None:
    """
    Free-text search hits both the source and the translation.
    """
    response = client.get("/locales/es/strings", params={"q": "arch"})
    assert response.status_code == 200
    assert "Archive" in response.text


def test_locale_strings_page_does_not_filter(client: TestClient) -> None:
    """
    The page shell ignores filter params; it is the shell, not the search target.
    """
    response = client.get("/locales/es", params={"variant": "verb"})
    assert response.status_code == 200
    # The shell renders every entry because the page does not run the filter.
    assert "Archivar" in response.text


def test_unknown_locale_returns_404(client: TestClient) -> None:
    """
    A locale that resolves to no file is a 404.
    """
    assert client.get("/locales/de").status_code == 404


def test_traversal_attempt_returns_404(client: TestClient) -> None:
    """
    A locale segment that fails the regex never reaches the filesystem.
    """
    assert client.get("/locales/..%2Fetc").status_code == 404


def test_edit_form_loads_an_entry(client: TestClient) -> None:
    """
    The edit form fragment carries the original text and the current values.
    """
    response = client.get("/locales/es/entry", params={"index": 0})
    assert response.status_code == 200
    assert "Archive" in response.text  # the original
    assert "Archivo" in response.text  # the current value


def test_new_form_loads(client: TestClient) -> None:
    """
    The "New string" form renders with empty fields.
    """
    response = client.get("/locales/es/entry/new")
    assert response.status_code == 200
    assert 'name="key"' in response.text


def test_update_via_htmx_persists_and_triggers_refresh(client: TestClient) -> None:
    """
    An HTMX POST edits an entry and the empty 204 carries the expected triggers.
    """
    response = client.post(
        "/locales/es/entry",
        data={"index": "0", "value": "El archivo", "variant": "noun", "draft": ""},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 204
    triggers = json.loads(response.headers["HX-Trigger"])
    assert "close-entry-dialog" in triggers
    assert "strings-refresh" in triggers

    # Reload from disk and verify the change landed.
    catalog = load_catalog(_dir(client), "es")
    assert catalog.rows[0].value == "El archivo"


def test_update_via_plain_form_redirects_with_toast(client: TestClient) -> None:
    """
    A non-HTMX submit redirects to the strings page with a flash toast.
    """
    response = client.post(
        "/locales/es/entry",
        data={"index": "0", "value": "El archivo", "variant": "noun", "draft": ""},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "toast=Saved." in response.headers["location"]


def test_update_collision_returns_422_with_form(client: TestClient) -> None:
    """
    Editing a variant into one already taken returns 422 with the form body so the error shows inline.
    """
    response = client.post(
        "/locales/es/entry",
        data={"index": "0", "value": "x", "variant": "verb", "draft": ""},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 422
    assert "variant" in response.text.lower()


def test_create_new_entry(client: TestClient) -> None:
    """
    Creating an entry appends it and surfaces a success toast.
    """
    response = client.post(
        "/locales/es/entry/new",
        data={"key": "Save", "value": "Guardar", "variant": "", "draft": ""},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 204
    catalog = load_catalog(_dir(client), "es")
    assert any(r.key == "Save" and r.value == "Guardar" for r in catalog.rows)


def test_create_duplicate_returns_422(client: TestClient) -> None:
    """
    A duplicate (key, variant) pair is refused with a 422.
    """
    response = client.post(
        "/locales/es/entry/new",
        data={"key": "Archive", "value": "x", "variant": "verb", "draft": ""},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 422
    assert "exists" in response.text


def test_delete_entry(client: TestClient) -> None:
    """
    A delete request drops the entry and announces success.
    """
    response = client.post(
        "/locales/es/entry/delete",
        data={"index": "4"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 204
    triggers = json.loads(response.headers["HX-Trigger"])
    assert "strings-refresh" in triggers
    catalog = load_catalog(_dir(client), "es")
    assert all(r.key != "My items" for r in catalog.rows)


def test_healthz_reflects_directory_state(translations_dir: Path) -> None:
    """
    /healthz returns a small JSON object describing the managed directory.
    """
    response = TestClient(create_app(Settings(translations_dir=translations_dir))).get("/healthz")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["directory"].endswith(translations_dir.name) or str(translations_dir) in payload["directory"]


def test_health_alias_reflects_directory_state(translations_dir: Path) -> None:
    """
    /health is an alias of /healthz, kept for monitors that default to it.
    """
    response = TestClient(create_app(Settings(translations_dir=translations_dir))).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_healthz_reports_missing_directory(tmp_path: Path) -> None:
    """
    An empty directory reports status=no-translations rather than erroring.
    """
    response = TestClient(create_app(Settings(translations_dir=tmp_path))).get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "no-translations"


# --- helpers ---------------------------------------------------------------


def _dir(client: TestClient) -> Path:
    """
    Reach back into the running app's settings to find the test directory.

    The app fixture calls ``create_app(Settings(...))`` directly, so the
    settings live on the app's private closure; the cleanest way to read them
    back is to call ``load_catalog`` with a directory we know about (the test
    function already received ``translations_dir`` in scope). However, for
    helpers used outside the ``translations_dir`` fixture we need a way to ask
    the client for it.

    Args:
        client: The Starlette TestClient.

    Returns:
        The directory the app was built with.
    """
    settings: Settings = client.app.state.settings  # type: ignore[attr-defined]
    return settings.translations_dir


def test_matches_filter_variants_no_variant_token() -> None:
    """
    The empty-string variant token matches entries with no variant.
    """
    row = EntryRow(index=0, key="Hello", value="Hola", variant=None, draft=False)
    assert matches_filter(row, [], EntryFilter(variants=("",)))
    assert not matches_filter(row, [], EntryFilter(variants=("verb",)))


def test_filter_rows_handles_empty_input() -> None:
    """
    Filtering an empty list is a no-op rather than a crash.
    """
    assert filter_rows([], EntryFilter(text="x")) == []
