# AGENTS.md

Context for AI agents (and humans) working on `fastapi-simple-i18n`.

## What this project is

A small internationalization library for FastAPI apps and CLI scripts. It
provides translations with variants and drafts, lazy translations, a locale
`ContextVar`, `Accept-Language` negotiation middleware, Babel-powered
number/date/time formatting, a registrable module system, and an AST-based
extraction script.

The public GitHub URL is `https://github.com/okelet/fastapi-simple-i18n`. The
importable package is `fastapi_simple_i18n`.

## Layout

```text
src/fastapi_simple_i18n/
    __init__.py            # empty (no re-exports); import from submodules
    models.py              # TranslationEntry, TranslationFile, Translation, dump_translation_file, ExtractedKey
    modules.py             # BaseModuleTranslation (ABC)
    locale.py              # current_locale ContextVar + get/set/reset + as_locale + default locale
    manager.py             # TranslationManager (registration + resolution)
    registry.py            # process-wide active manager (module global, NOT a ContextVar)
    helpers.py             # TranslatableStr + LazyTranslatableStr + t/lazy_t and formatters
    negotiation.py         # parse_accept_language, negotiate_locale
    middleware.py          # TranslationMiddleware (pure ASGI)
    jinja.py               # Jinja2 runtime helpers + template extraction (optional 'jinja' extra)
    extract_translations.py# AST/Jinja extraction CLI (python -m ...)
    web/                   # Translation file web UI (FastAPI + HTMX + Alpine)
        __init__.py        # no top-level re-exports; import from submodules
        app.py             # FastAPI app factory + routes
        config.py          # Settings (FSI_WEB_* env prefix, pydantic-settings)
        catalog.py         # pure helpers: read locale files, fold/filter/paginate, placeholders
        storage.py         # write side: atomic temp+rename + CRUD helpers
        templates/         # base.html, locales.html, strings.html, partials/_results.html, partials/_entry_form.html
        static/            # favicon
examples/
    fastapi_app/           # runnable FastAPI example (i18n.py, main.py, templating.py, templates/, translations/)
    cli_app/               # runnable CLI example
tests/                     # pytest suite (absolute imports here are fine)
docs/                      # MkDocs site
```

## Key design decisions

* The **active manager is a process-wide module global** in `registry.py`, not a
  `ContextVar`. This is deliberate: Starlette's `BaseHTTPMiddleware` runs the
  endpoint in a separate context, so a ContextVar-stored manager set during
  middleware construction was not visible to endpoints on later requests. Only
  the **locale** is per-request (a `ContextVar` in `locale.py`).
* `t()` returns a `TranslatableStr`, a `str` subclass carrying the translated
  text. The lookup happens at call time, against the locale active *then*;
  the result is a real `str` so it works anywhere a string is expected
  (`json.dumps`, Pydantic str fields, `quote()`, concatenation, `| tojson` in
  Jinja) with no `str()` wrapper. `lazy_t()` returns a `LazyTranslatableStr`
  (NOT a `str` subclass) that defers the lookup until render — use it when
  the value is captured at a point where the locale is not yet known
  (module-level constants, decorators that run before the request) and the
  locale may change later; wrap with `str()` at JSON / Pydantic / `| tojson`
  boundaries.
* The unique unit of a translation is the pair `(key, variant)`.
* Resolution: built-in locale returns the key verbatim (variant ignored);
  otherwise look up `(key, variant)`; drafts are used as-is; missing keys fall
  back to the key and log a warning.
* Placeholders use `str.format` (`{name}`), not ICU MessageFormat. No
  pluralization beyond what `format` provides.
* The JSON file format is `{"translations": [ {key, value, variant?, draft?} ]}`.
  `dump_translation_file` omits `variant`/`draft` when unset.
* Templates are served by `jinja.py` through a plain installer function rather
  than a Jinja `Extension`, because extensions cannot take configuration
  arguments and the function/filter names are configurable. The configuration is
  stored on the environment with `setattr` (`environment.extend()` silently
  ignores attributes that already exist) so the extraction script can read the
  same names the application renders with.
* The template callable is decorated with `@pass_context` **on purpose**: Jinja
  constant-folds a *filter* call whose arguments are all literals while
  compiling, so a plain function would translate `{{ "Key" | t }}` once, with
  whatever locale was active at compile time, and every later request would reuse
  that string. A context-taking callable is never folded.
* `{% trans %}` is Jinja's own tag, so it interpolates with `%(name)s`, not
  `{name}`, and it cannot express a variant; a block context maps to one.
  Pluralization is deliberately unsupported and fails loudly on both the runtime
  and the extraction path rather than half-working.
* The translation function and the filter accept **one name or several**, and a
  call matches on the name alone in both extractors, so `helpers.t("Key")` and
  `{{ i18n.t("Key") }}` are found without any configuration. The
  `--python-function`, `--jinja-function` and `--jinja-filter` options are
  repeatable and *replace* (never extend) the default or stored names. This is
  what covers wrapper helpers and aliased imports. `run()` prints the names it
  used, so a name that does not match shows up instead of silently extracting
  nothing.
* Template files are matched by `has_suffix()` in `modules.py`, which tests the
  whole file name with `str.endswith`, **not** `pathlib.Path.suffix`. That is
  what makes compound suffixes such as `.html.j2` and `.j2.html` work;
  `Path.suffix` only ever returns the last part. Each extractor owns its own
  `handles()` predicate, and `scan_dirs` takes that predicate, so the file
  selection rule lives next to the parsing it belongs to.

## Conventions

Python:

* Python 3.14+. Modern typing (`list[X]`, `X | None`).
* Relative imports inside `src/` (e.g. `from .manager import ...`). Tests use
  absolute imports.
* Docstrings on every module, class, function, and inner function, with the
  triple quotes on their own lines.
* Top-level imports only.
* Line length 320 (ruff/pylint/isort).

Markdown:

* Blank line after every heading.
* Blank line before and after each bullet group.
* Prefer `*` for top-level list items.
* Avoid unnecessary horizontal rules (`---`).
* Every fenced code block must declare a language; use `text` when there is no
  applicable language.

All docs, comments, and docstrings are in English.

## Validation

Run the checks with `uv run` (it resolves and syncs the environment from
`pyproject.toml` automatically, including the `dev` dependencies):

```bash
uv run ruff check src tests examples
uv run isort --check-only src tests examples
uv run pylint src/fastapi_simple_i18n
uv run pytest
```

Dependency groups (PEP 735, run with `uv run --group <name>`):

* `web` — `fastapi` + `jinja2` + `pydantic-settings` + `python-multipart` + `uvicorn`,
  to run the translation web UI (`fastapi_simple_i18n.web.app`).
* `examples` — `fastapi` + `jinja2` + `uvicorn`, to run the example app/CLI.
* `docs` — `mkdocs` + `mkdocs-material`, to build/serve the docs.

The `dev` extra holds only test/lint tooling; mkdocs is intentionally not there.
`starlette.testclient.TestClient` needs an HTTP client, and Starlette 1.6+
prefers `httpx2` (Pydantic's continuation of HTTPX) over `httpx`, warning when
only `httpx` is installed. So the dev group requires `httpx2`, not `httpx`.
Note that `StarletteDeprecationWarning` subclasses `UserWarning`, so the
`filterwarnings = ["ignore::DeprecationWarning"]` in `pyproject.toml` does not
silence it. The dev group also carries `jinja2`, because `tests/test_jinja.py`
imports `fastapi_simple_i18n.jinja` directly.

Optional dependency extras, each needed by exactly one module:

* `fastapi-simple-i18n[fastapi]` adds `starlette`, needed **only** by
  `middleware.py` (the sole module importing Starlette).
* `fastapi-simple-i18n[jinja]` adds `jinja2`, needed **only** by `jinja.py` (the
  sole module importing Jinja2).

Both raise an actionable `ImportError` when missing. The core runtime dependency
is just `babel`. Because `extract_translations.py` must keep working without
Jinja2, it imports `jinja.py` on demand with `importlib`, and only when a module
actually declares template directories, instead of with a top-level import.

Current status: ruff clean, isort clean, pylint 10.00/10, 151 tests passing (43 in
`tests/test_web.py` for the web UI), with no warnings.

Note: `registry.py` and `locale.py` each carry one intentional module-level
mutable global (`_current_manager`, `_default_locale`) with a
`# pylint: disable=invalid-name` comment. Do not "fix" these into UPPER_CASE;
they are reassigned at runtime.

## Manual checks that exercise the whole system

```bash
# FastAPI example
uv run --group examples python -c "from starlette.testclient import TestClient; from examples.fastapi_app.main import app; c=TestClient(app); print(c.get('/', headers={'Accept-Language':'es'}).json()); print(c.get('/?lang=fr').json())"

# Jinja template route of the FastAPI example (one line per locale, order matters:
# the first request compiles the template, later ones reuse the cached compilation)
uv run --group examples python -c "from starlette.testclient import TestClient; from examples.fastapi_app.main import app; c=TestClient(app); [print(loc, c.get('/page?name=Ada&items=3', headers={'Accept-Language': loc}).text) for loc in ('es','fr','en')]"

# CLI example
uv run --group examples python -m examples.cli_app.main --locale es

# Extraction (dry run) against the example module
uv run python -m fastapi_simple_i18n.extract_translations examples.fastapi_app.i18n:AppTranslation --dry-run

# Extraction with renamed template helpers, ignoring the module's environment.
# Both options are repeatable; the count must stay the same as the plain run,
# because every template-only key in the example comes from {% trans %}.
uv run python -m fastapi_simple_i18n.extract_translations examples.fastapi_app.i18n:AppTranslation --jinja-function translate --jinja-function t --jinja-filter tx --jinja-filter t --dry-run

# Extraction of a Python function reached through an alias or a wrapper. The
# example's i18n.py has no wrapper, so only the t() key is expected here.
uv run python -m fastapi_simple_i18n.extract_translations examples.fastapi_app.i18n:AppTranslation --python-function tr --python-function t --dry-run

# Docs (preview / build)
uv run --group docs mkdocs serve
uv run --group docs mkdocs build --strict
```

# Translation web UI
uv run --group web python -c "from starlette.testclient import TestClient; from fastapi_simple_i18n.web.app import create_app; from fastapi_simple_i18n.web.config import Settings; app=create_app(Settings(translations_dir='examples/fastapi_app/translations')); c=TestClient(app); print(c.get('/').status_code, c.get('/locales/es').status_code, c.get('/healthz').json())"
```

## Translation web UI

`src/fastapi_simple_i18n/web/` is a small FastAPI + Jinja2 + HTMX + Alpine UI that
reads and edits the locale JSON files directly — no database, no migration,
no second format. It exists in this repo because the developer tool that
helped write the library deserves to ship with it, but it is a **development
tool**: its dependencies are a PEP 735 group, not a published wheel extra.

### Running it

```bash
uv sync --group web
FSI_WEB_TRANSLATIONS_DIR=/path/to/translations \\
    uv run --group web uvicorn fastapi_simple_i18n.web.app:app
```

The directory is the only configuration knob (`FSI_WEB_TRANSLATIONS_DIR`,
defaults to `./translations`). The UI shows every `*.json` in that directory
as a locale; each opens a strings page with a free-text search, a variant
multiselect, a draft tri-state, pagination, and per-row Edit / Delete /
"New string" actions. Writes go through `storage.write_entries`, which writes
to a temporary file in the same directory and then `os.replace`s it onto the
target so a crash mid-save never leaves a truncated JSON behind.

### Layout

* `web/config.py` — pydantic-settings (`FSI_WEB_TRANSLATIONS_DIR`,
  `FSI_WEB_PAGE_SIZE`, `FSI_WEB_SITE_TITLE`).
* `web/catalog.py` — read-only helpers. No I/O at import time, no globals:
  `list_locales`, `load_catalog`, `filter_rows`, `paginate`, `placeholder_issues`,
  `collect_variants`, `flag_emoji`, `locale_display_name`, `locale_path`. The
  latter is the path-traversal guard (a regex; no dot, no separator, no NUL).
* `web/storage.py` — write side. `load_entries`, `create_entry`, `update_entry`,
  `delete_entry`, `write_entries`. Mutations are pure (return a new list) and
  the persist step is atomic.
* `web/app.py` — FastAPI factory + routes. Mounts `/static`, serves
  `/healthz`, returns a 204 + `HX-Trigger` for HTMX success (close dialog,
  refresh table, raise toast) and a 422 carrying the re-rendered form on
  validation failure. The form fragment lives in
  `web/templates/partials/_entry_form.html` and is shared between Edit and
  Create; `mode` selects the action and the posted fields.
* `web/templates/base.html` — shared shell. Inline `<head>` script applies
  the stored theme (light / dark / system, in `localStorage.themeMode`) before
  first paint to avoid a flash; Alpine's `themePicker` component keeps the
  `dark` class in sync with `matchMedia('(prefers-color-scheme: dark)')`. The
  dialog is a native `<dialog>` with `dialog.showModal()` from JS and
  `dialog.close()` on the `HX-Trigger: {"close-entry-dialog": ...}` response,
  which gets free focus trapping and `Esc`-to-close.

### Key design decisions

* **No second format.** The UI calls `dump_translation_file` (the same
  serializer the extraction script uses) so re-saving an unchanged file is a
  no-op on disk and round-trips through `TranslationFile.from_json` byte for
  byte. New entries land at the end of the file in creation order; existing
  entries are edited in place, so a one-line edit is a one-line diff in git.
* **Server-side filtering, Alpine-driven shell.** The filter form posts to
  `GET /locales/{locale}/strings` and HTMX swaps `#strings-result`. The
  page shell and the form never re-render, so the form's Alpine state (text,
  selected variants, draft tri-state, page) survives every search. The URL
  is mirrored via `history.replaceState`, so reloading the page preserves the
  filters without flooding the back button.
* **The variant multiselect reserves the empty string** for "no variant".
  An entry with `variant = None` matches the empty option; an entry with a
  real variant matches the option carrying that exact string. Two separate
  entries with the same `(key, variant)` pair are refused at save time
  rather than silently dropped (the editor's view, where duplicates matter,
  differs from the library's runtime index, which silently dedupes).
* **Tristate is a native `<select>`, not a custom widget.** The user asked
  for a "tristate select" specifically; a `<select>` is accessible, mobile-
  friendly and works without JavaScript. The variant multiselect is Alpine-
  driven because a native `<select multiple>` is genuinely unusable; that
  same pattern was copied from `wallet-summary`.
* **Placeholders are checked and flagged in the table.** Every row with a
  placeholder mismatch (a `{name}` in the source missing from the value, or
  vice versa) shows a red badge next to the translation. Both
  `str.format` (`{name}`) and `gettext` (`%(name)s`) are recognised.
* **The dialog is a native `<dialog>`.** It gets `Esc`-to-close, focus
  trapping and the top layer for free, and we open it with
  `dialog.showModal()` so its z-index never fights a dropdown.
* **Errors are re-rendered into the form (HTTP 422).** A base-level
  `htmx:beforeSwap` handler opts 422 responses into the swap, the same
  pattern as `wallet-summary`. The user therefore sees inline validation
  errors instead of an invisible "nothing happened" failure.

### Things deliberately out of scope

* **No auth.** The tool is meant to run behind a reverse proxy or on a
  developer's machine; if it is exposed to the internet, gate it at the
  proxy.
* **No editor for the JSON itself (rename, reorder, batch delete).** Adding
  those is straightforward but goes beyond "minima".
* **The UI is English.** Dogfooding the library's own `t()` is the obvious
  improvement, but the UI runs in the same environment it manages, which
  raises a chicken-and-egg question worth resolving first.

## Ideas for future work

* Optional ICU MessageFormat support for pluralization/gender. That is the
  natural way to make `{% pluralize %}` work.
* A Jinja2 loader-aware extraction mode, so templates that build names
  dynamically (a `{% include %}` target only known at runtime) are covered.
* HTML in the catalog: today autoescape escapes the whole translated string, so a
  translation cannot contain markup. A `@pass_context` wrapper that escapes only
  the interpolated values and returns `Markup` would enable it, at the cost of
  trusting translator-supplied HTML.
* Caching of parsed locale files if very large.
* A `pytest` plugin fixture to configure a manager for tests.
