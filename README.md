# fastapi-simple-i18n

Simple, module-friendly internationalization for FastAPI apps and CLI scripts.

It provides a small translation system built around a `TranslationManager`,
JSON translation files (with support for variants and drafts), lazy translation
objects, a locale `ContextVar`, `Accept-Language` negotiation middleware, and
Babel-powered number/date/time formatting.

## Features

* A `TranslationManager` where you register translation files or whole modules.
* A per-locale `Translation` object backed by a simple JSON file format.
* Translation entries support an optional `variant` (to disambiguate identical
  keys) and a `draft` flag (used at runtime, marked for later review).
* Lazy translations: `t()` returns an object that resolves to a string only
  when rendered, so the active locale is read at render time.
* A locale `ContextVar` with `set_current_locale` / `get_current_locale`.
* FastAPI/Starlette middleware that negotiates the locale from the
  `Accept-Language` header, with configurable default and built-in locales.
* Babel helpers: `t_number`, `t_date`, `t_time`, `t_datetime`.
* Registrable translation modules via `BaseModuleTranslation`.
* An AST-based extraction script that finds `t("...")` calls and updates locale
  files, marking new strings as drafts and preserving existing translations.
* Jinja2 templates: `t()`, a `t` filter and `{% trans %}` blocks resolve against
  the same catalog, with configurable names.
* A translation file web UI (FastAPI + HTMX + Alpine) that browses and edits
  the locale JSON files directly, ships in the `web` dependency group.
* Works in CLI scripts by configuring the manager and locale manually.

## Installation

Install directly from GitHub with `uv`:

```bash
uv add "git+https://github.com/okelet/fastapi-simple-i18n"
```

The core package depends only on `babel`. Two modules are optional:

* `fastapi_simple_i18n.middleware` is the only module that needs Starlette, so
  FastAPI apps should install the `fastapi` extra (Starlette comes with FastAPI
  anyway).
* `fastapi_simple_i18n.jinja` is the only module that needs Jinja2, so apps with
  templates should install the `jinja` extra.

```bash
uv add "fastapi-simple-i18n[fastapi] @ git+https://github.com/okelet/fastapi-simple-i18n"
uv add "fastapi-simple-i18n[jinja] @ git+https://github.com/okelet/fastapi-simple-i18n"
```

CLI-only projects can skip both. Importing one of those modules without its
dependency raises an `ImportError` telling you what to install.

## Quick start (FastAPI)

```python
from fastapi import FastAPI

from fastapi_simple_i18n.helpers import t
from fastapi_simple_i18n.locale import get_current_locale
from fastapi_simple_i18n.manager import TranslationManager
from fastapi_simple_i18n.middleware import TranslationMiddleware

from myapp.i18n import AppTranslation

manager = TranslationManager(builtin_locale="en")
manager.register_translation(AppTranslation)

app = FastAPI()
app.add_middleware(
    TranslationMiddleware,
    manager=manager,
    default_locale="en",
    builtin_locale="en",
)


@app.get("/")
async def index() -> dict[str, str]:
    return {
        "locale": get_current_locale(),
        "greeting": str(t("Hello, {name}!", name="Ada")),
    }
```

## Quick start (CLI)

```python
from fastapi_simple_i18n.helpers import t
from fastapi_simple_i18n.locale import set_current_locale, set_default_locale
from fastapi_simple_i18n.manager import TranslationManager
from fastapi_simple_i18n.registry import set_translation_manager

from myapp.i18n import AppTranslation

manager = TranslationManager(builtin_locale="en")
manager.register_translation(AppTranslation)
set_translation_manager(manager)
set_default_locale("en")
set_current_locale("es")

print(t("Hello, {name}!", name="Ada"))
```

## Translation file format

Each locale is a JSON file with a `translations` list. Every entry has a `key`
and a `value`, plus an optional `variant` and an optional `draft` flag:

```json
{
  "translations": [
    { "key": "Yes", "value": "Sí" },
    { "key": "Archive", "value": "Archivar", "variant": "verb" },
    { "key": "Archive", "value": "Archivo", "variant": "noun" },
    { "key": "My items", "value": "Mis elementos", "draft": true }
  ]
}
```

The built-in locale (the language the source strings are written in) needs no
file: its keys are returned verbatim.

## Extracting strings

Run the AST-based extraction script against a module translation class:

```bash
uv run python -m fastapi_simple_i18n.extract_translations myapp.i18n:AppTranslation
uv run python -m fastapi_simple_i18n.extract_translations myapp.i18n:AppTranslation es fr
uv run python -m fastapi_simple_i18n.extract_translations myapp.i18n:AppTranslation --prune
uv run python -m fastapi_simple_i18n.extract_translations myapp.i18n:AppTranslation --dry-run
```

New `(key, variant)` pairs are added with an empty value and `draft: true`;
existing translations are preserved.

If your code calls the translation function under another name — an aliased
import or a wrapper of your own — name it, once per name:

```bash
uv run python -m fastapi_simple_i18n.extract_translations myapp.i18n:AppTranslation \
    --python-function t --python-function translate
```

## Templates

With the `jinja` extra, templates translate strings the same way Python code
does — same `t()`, same variants, same `{name}` placeholders — and their strings
land in the same catalog:

```python
from fastapi.templating import Jinja2Templates
from fastapi_simple_i18n.jinja import install_translation_support

templates = Jinja2Templates(directory="templates")
install_translation_support(templates.env)  # names are configurable
```

```html
<p>{{ t("Hello, {name}!", name=user.name) }}</p>
<p>{{ "Archive" | t(variant="verb") }}</p>
<p>{% trans %}Signed in{% endtrans %}</p>
<p>{% trans "noun" %}Archive{% endtrans %}</p>
```

Point your module's `get_template_dirs()` at the templates and the extraction
script parses them with Jinja's own parser, never a regex. The function and the
filter take any name, and several of them, so wrappers and aliased imports are
extracted too. See [Templates](docs/jinja.md) for the details, including the
two things that differ from Python (`{% trans %}` interpolates with `%(name)s`,
and pluralization is not supported).

## Examples

The `examples/` directory contains a runnable FastAPI app and a CLI script.

The FastAPI example needs `fastapi` and `uvicorn`, which live in the `examples`
dependency group. Run it with `uv run --group` so those are available:

```bash
uv run --group examples uvicorn examples.fastapi_app.main:app --reload
```

Run the CLI example:

```bash
uv run --group examples python -m examples.cli_app.main --locale es
```

## Translation file web UI

`src/fastapi_simple_i18n/web/` ships a small FastAPI + Jinja2 + HTMX + Alpine
app that browses and edits the locale JSON files directly, no database. It is
a developer tool that ships with the repository, not a published extra: its
dependencies live in the `web` dependency group.

```bash
FSI_WEB_TRANSLATIONS_DIR=/path/to/translations uv run --group web uvicorn fastapi_simple_i18n.web.app:app
```

The directory holds one `*.json` per locale (the same format
`dump_translation_file` writes). The UI shows every locale with its entry /
draft / untranslated counts; each opens a strings page with a free-text
search, a variant multiselect (with a "(no variant)" option for entries that
carry no variant), a draft tri-state, server-side pagination, and per-row
Edit / Delete / "New string" actions. Placeholder mismatches between the
source string and the translation are flagged inline. Writes are atomic
(temp + `os.replace`) and the same serializer the extraction script uses,
so re-saving an unchanged file is a no-op on disk.

Configuration is read from `FSI_WEB_*` environment variables
(`FSI_WEB_TRANSLATIONS_DIR`, `FSI_WEB_PAGE_SIZE`, `FSI_WEB_SITE_TITLE`). The
tool is meant to run behind a reverse proxy or on a developer's machine; it
ships no auth.

## Documentation

Full documentation lives in `docs/` and is built with
[MkDocs](https://www.mkdocs.org/) and
[Material for MkDocs](https://squidfunk.github.io/mkdocs-material/). The tooling
lives in the `docs` dependency group, so run it with `uv run --group docs`:

```bash
uv run --group docs mkdocs serve   # preview at http://127.0.0.1:8000
uv run --group docs mkdocs build   # build the static site into site/
```

See [Building the docs](docs/building-docs.md) for more.

## Development

The `dev` dependency group holds the test and lint tooling. `uv run` resolves
and syncs it automatically (the `dev` group is installed by default), so no
manual install step is needed:

```bash
uv run ruff check src tests examples
uv run isort --check-only src tests examples
uv run pylint src/fastapi_simple_i18n
uv run pytest
```

## Development note

This code was developed mostly with AI (vibe coding), but has been reviewed and
validated by a human.

## License

MIT.
