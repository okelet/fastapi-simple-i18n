# AGENTS.md

Context for AI agents (and humans) working on `fastapi-simple-i18n`.

## What this project is

A small internationalization library for FastAPI apps and CLI scripts. It
provides translations with variants and drafts, eager and lazy translations,
locale and timezone `ContextVar`s, `Accept-Language` negotiation middleware,
Babel-powered number/amount/date/time formatting, a registrable module system,
and an AST-based extraction script.

The public GitHub URL is `https://github.com/okelet/fastapi-simple-i18n`. The
importable package is `fastapi_simple_i18n`.

## Layout

```text
src/fastapi_simple_i18n/
    __init__.py            # empty (no re-exports); import from submodules
    models.py              # TranslationEntry, TranslationFile, Translation, dump_translation_file, ExtractedKey
    modules.py             # BaseModuleTranslation (ABC)
    locale.py              # resolve_locale + current_locale ContextVar + get/set/reset + as_locale + default locale
    timezone.py            # resolve_timezone + current_timezone ContextVar + get/set/reset + as_timezone + UTC default
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
  the **locale** and the **timezone** are per-request (`ContextVar`s in
  `locale.py` and `timezone.py`).
* **Locales are `babel.core.Locale` objects**, not strings, and there is no
  library-specific locale class or exception. `resolve_locale(locale)` is the
  single entry point: it accepts a `Locale` (returned as-is) or a tag in any
  spelling (`es`, `es_ES`, `es-ES`, `ES-es`, `zh_Hans_CN`, `en_US_POSIX`, with
  surrounding blanks), and raises `ValueError` for an empty value, a tag mixing
  `_` and `-`, a malformed tag, or an unknown one. Every setter
  (`set_default_locale`, `set_current_locale`, `TranslationManager.builtin_locale`)
  and every locale-taking helper validates on the way in, so a typo fails where
  it is written. `get_current_locale()` never returns `None`. Consequences to
  keep in mind: `Locale == "es"` is `False` (compare with another `Locale`), and
  `json.dumps(Locale)` fails, so JSON payloads need `str(get_current_locale())`.
* **There is always a timezone.** `timezone.py` mirrors `locale.py` exactly:
  `resolve_timezone(tzinfo | str) -> tzinfo` is the single entry point, every
  setter validates, and `get_current_timezone()` never returns `None`. The
  process-wide default starts at `DEFAULT_TIMEZONE` (`ZoneInfo("UTC")`, resolved
  through `resolve_timezone` so it is identical to what a caller passing
  `"UTC"` gets) and cannot be unset. `None` is refused by `set_current_timezone`,
  `set_default_timezone` and `as_timezone` alike — a moment rendered in the
  process local zone is a moment whose wall clock depends on where the server
  runs, which is the thing this removes. The one `None` left in the module is
  the `ContextVar`'s own "not resolved in this context" marker; it is what makes
  `reset_current_timezone` and the middleware's per-request reset work, and it is
  never visible through a getter. A formatter's `tz=` argument keeps `None` as
  its default, where it means "the active one" (there is no longer a "none" to
  express), and an explicit value is validated when it is used.
* The **manager keys translations by the resolved `Locale`**, and
  `supported_locales()` returns `set[Locale]`. Babel's `Locale.__eq__` compares
  subtags, so all spellings of a locale collapse onto one entry. The *file* name
  on disk is kept as written, because that is the name a translator sees in git
  and in the web UI.
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
* `t_money(value, currency)` formats an amount with its currency symbol and
  `t_amount(value)` the same amount without one (for sums that mix currencies);
  both default to `MONEY_FORMAT = "#,##0.00"`, unlike `t_number`'s
  `"#,##0.###"`. A blank or unrecognised currency code degrades to a plain
  localized decimal and logs a warning, so a mistyped code never breaks a
  rendered page. There is no locale fallback in these helpers: locales are
  validated at every entry point, so the only thing that can fail is the
  currency.
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
* The installer also registers two read-only context globals,
  `get_current_locale` (a `babel.core.Locale`) and `get_current_tz` (a
  `tzinfo`, never `None`), from `CONTEXT_HELPERS`, so a template does not need
  the locale or the timezone threaded through its render context. They go in
  with `environment.globals.setdefault`, so an application that defines its own
  global of that name keeps it. Note that `{{ get_current_locale() }}` renders
  the Babel identifier (`es_ES`), while `<html lang=...>` wants
  `{{ get_current_locale().language }}`.
* Negotiation matches on the resolved locale too: a candidate matches a
  supported locale exactly, or its base language when a supported locale *is*
  that bare language. So `es-MX` never lands on a supported `es_ES`, while
  `es-MX` with a supported `es` does.
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
* Top-level imports only, in `src`, `tests` and `examples` alike.
* Line length 320 (ruff/pylint/isort).
* pytest fixtures shadowing an outer name (`translations_dir`, `app`,
  `client` in `tests/test_web.py`) are declared with an explicit
  `@pytest.fixture(name="...")` on a `*_fixture`-suffixed function, so pylint
  does not report `redefined-outer-name` and the name inside the function
  matches the one tests request.

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
uv run pylint src/fastapi_simple_i18n tests
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

Current status: ruff clean, isort clean, pylint 10.00/10 over `src` and
`tests`, 274 tests passing (44 in `tests/test_web.py` for the web UI), with no
warnings.

Note: `registry.py`, `locale.py` and `timezone.py` each carry one intentional
module-level mutable global (`_current_manager`, `_default_locale`,
`_default_timezone`) with a `# pylint: disable=invalid-name` comment. Do not
"fix" these into UPPER_CASE; they are reassigned at runtime.
`timezone.DEFAULT_TIMEZONE` is the opposite case: it *is* `UPPER_CASE`, because
it is a constant, and it is resolved through `resolve_timezone` at import so it
is the same object a caller passing `"UTC"` gets.

## Manual checks that exercise the whole system

```bash
# FastAPI example
uv run --group examples python -c "from starlette.testclient import TestClient; from examples.fastapi_app.main import app; c=TestClient(app); print(c.get('/', headers={'Accept-Language':'es'}).json()); print(c.get('/?lang=fr').json())"

# Number / money / date / time formatting, with and without an explicit timezone
uv run --group examples python -c "from starlette.testclient import TestClient; from examples.fastapi_app.main import app; c=TestClient(app); [print(loc, c.get('/formats', headers={'Accept-Language': loc}).json()) for loc in ('es','en')]"

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

# Translation web UI
uv run --group web python -c "from starlette.testclient import TestClient; from fastapi_simple_i18n.web.app import create_app; from fastapi_simple_i18n.web.config import Settings; app=create_app(Settings(translations_dir='examples/fastapi_app/translations')); c=TestClient(app); print(c.get('/').status_code, c.get('/locales/es').status_code, c.get('/healthz').json())"

# Docs (preview / build)
uv run --group docs mkdocs serve
uv run --group docs mkdocs build --strict
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
  `locale_display_name` and `flag_emoji` go through the library's
  `resolve_locale`, so an `es_ES.json` file gets the same display name and flag
  as an `es-ES.json` one, and a stem that is not a locale at all is shown
  as-is instead of blowing up the page.
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
