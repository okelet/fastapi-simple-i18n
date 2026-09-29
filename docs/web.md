# Translation file web UI

`fastapi_simple_i18n.web` ships a small FastAPI + Jinja2 + HTMX + Alpine
app that browses and edits the locale JSON files directly. There is no
database, no migration, and no second file format: the UI calls
`dump_translation_file` (the same serializer the extraction script uses), so
re-saving an unchanged file is a no-op on disk.

The module lives in the repository as a developer tool, not a published
extra: its dependencies are a PEP 735 group, run with
`uv run --group web …`. Run it with `uvicorn`:

```bash
uv sync --group web
FSI_WEB_TRANSLATIONS_DIR=/path/to/translations \
    uv run --group web uvicorn fastapi_simple_i18n.web.app:app
```

## Configuration

Every setting is prefixed with `FSI_WEB_`:

| Variable | Default | Description |
| --- | --- | --- |
| `FSI_WEB_TRANSLATIONS_DIR` | `./translations` | Directory the UI manages. May not exist yet; the UI then shows a hint instead of failing. |
| `FSI_WEB_PAGE_SIZE` | `50` | Entries per page in the strings table. |
| `FSI_WEB_SITE_TITLE` | `Translations` | Title shown in the navigation bar and the browser tab. |

The locale name comes from the file stem (`es.json` → locale `es`); the
filename pattern is validated against `^[A-Za-z0-9_-]+$`, so a crafted
locale can never escape the directory.

## Features

* **Locales index** at `/`: every `*.json` in the configured directory, with
  entry / draft / untranslated counts, size and last-modified timestamp.
  Parse errors are surfaced as a red badge on the row instead of crashing
  the page.
* **Strings page** at `/locales/{locale}`: server-side filtered table with
  free-text search (accent- and case-insensitive, matches both the source
  and the translation), a variant multiselect with a "(no variant)" option,
  a draft tri-state, pagination, and per-row Edit / Delete / "New string"
  actions.
* **Edit dialog**: a native `<dialog>` carrying the original string as a
  read-only reference, a `<textarea>` for the translation, a `<datalist>`-
  backed variant field, and a "Mark as draft" checkbox. Save / Cancel in the
  footer.
* **Light / dark / system** theme selector (persisted in `localStorage` under
  `themeMode`), with an inline `<head>` script that applies the chosen theme
  before first paint so the page never flashes the wrong colour.
* **Atomic writes**: every edit goes through a temporary file in the same
  directory + `os.replace`, so a crash mid-save never leaves a truncated
  JSON behind.
* **Validation**: a duplicate `(key, variant)` pair is refused with a 422
  carrying the form back into the dialog (HTMX's `htmx:beforeSwap` handler
  opts 422 into the swap), so the user sees the error inline instead of a
  silent failure.
* **Placeholder checks**: every row flags mismatches between the source's
  `{name}` / `%(name)s` placeholders and the translation's, in red, so a
  translator is warned before a missing placeholder crashes a render.

## Production notes

* **No auth.** The tool is meant to run behind a reverse proxy or on a
  developer's machine; if it is exposed to the internet, gate it at the
  proxy.
* **Tailwind via CDN.** The UI uses the Play CDN; for an internet-facing
  deployment, build a production Tailwind bundle instead (the templates are
  already grouped under `web/templates/`).
* **The UI is not translated.** Dogfooding the library's own `t()` is the
  obvious follow-up, but the UI runs in the same environment it manages,
  which raises a chicken-and-egg question worth resolving first.