# API reference

This page summarizes the public API. Import each symbol from its submodule (the
top-level `fastapi_simple_i18n` package deliberately re-exports nothing):

* [`fastapi_simple_i18n.helpers`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/helpers.py) — `t`, `t_number`, `t_date`, `t_time`, `t_datetime`, `LazyTranslation`
* [`fastapi_simple_i18n.manager`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/manager.py) — `TranslationManager`
* [`fastapi_simple_i18n.middleware`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/middleware.py) — `TranslationMiddleware`
* [`fastapi_simple_i18n.models`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/models.py) — `Translation`, `TranslationEntry`, `TranslationFile`, `TranslationFormatError`, `dump_translation_file`
* [`fastapi_simple_i18n.modules`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/modules.py) — `BaseModuleTranslation`
* [`fastapi_simple_i18n.locale`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/locale.py) — `get_current_locale`, `set_current_locale`, `reset_current_locale`, `as_locale`, `get_default_locale`, `set_default_locale`, `current_locale`
* [`fastapi_simple_i18n.registry`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/registry.py) — `get_translation_manager`, `set_translation_manager`, `has_translation_manager`
* [`fastapi_simple_i18n.negotiation`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/negotiation.py) — `parse_accept_language`, `negotiate_locale`
* [`fastapi_simple_i18n.jinja`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/jinja.py) — `install_translation_support`, `build_default_environment`, `get_jinja_config`, `JinjaConfig`, `JinjaExtractor`, `TemplateCallVisitor`
* [`fastapi_simple_i18n.extract_translations`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/extract_translations.py) — the extraction script: `TranslationCallVisitor`, `extract_from_python_file`, `PythonExtractor`, `TemplateExtractor`, `build_template_extractor`, `merge_keys_into_translation`, `resolve_module`, `run`, `main`

Only `fastapi_simple_i18n.middleware` needs Starlette (`fastapi-simple-i18n[fastapi]`); importing it without Starlette raises an `ImportError` that says which extra to install. Only `fastapi_simple_i18n.jinja` needs Jinja2 (`fastapi-simple-i18n[jinja]`), and importing it without Jinja2 raises the same kind of `ImportError`.

## Translation helpers

Source: [`helpers.py`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/helpers.py)

`t(key, _variant=None, **params) -> LazyTranslation`

Return a lazy translation. It resolves to the translated string when converted
with `str()`, applying `**params` via `str.format`. Use `_variant` to select a
variant.

`t_number(value, locale=None) -> str`

Format a number for the current (or given) locale.

`t_date(value, format="medium", locale=None) -> str`

Format a date. `format` is `"short"`, `"medium"`, `"long"`, `"full"`, or a Babel
pattern.

`t_time(value, format="short", locale=None) -> str`

Format a time.

`t_datetime(value, format="medium", locale=None) -> str`

Format a datetime.

## LazyTranslation

Source: [`helpers.py`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/helpers.py)

The object returned by `t()`. Notable members:

* `resolve(locale=None) -> str` — resolve explicitly, optionally overriding the
  locale.
* `__str__` — resolve using the current locale.
* Equality against a plain string compares the resolved value.

## TranslationManager

Source: [`manager.py`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/manager.py)

* `TranslationManager(builtin_locale="en")` — create a manager.
* `register_translation(module)` — load all locales exposed by a
  `BaseModuleTranslation` subclass.
* `add_translation(translation)` — register/merge a `Translation`.
* `add_entries(locale, entries)` — register a list of `TranslationEntry`.
* `get_translation(locale)` — return the `Translation` for a locale, if any.
* `supported_locales()` — the set of locales served (includes the built-in one).
* `translate(key, variant=None, locale=None)` — resolve a key to a string.

## Locale context

Source: [`locale.py`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/locale.py)

* `get_current_locale()` — the effective locale (forced value, else default).
* `set_current_locale(locale)` — force the locale; returns a token.
* `reset_current_locale(token)` — restore the previous locale.
* `as_locale(locale)` — context manager that forces `locale` for a `with` block
  and restores the previous value on exit (even on exceptions).
* `get_default_locale()` / `set_default_locale(locale)` — the process default.
* `current_locale` — the underlying `ContextVar`.

## Registry

Source: [`registry.py`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/registry.py)

* `set_translation_manager(manager)` — set the active manager.
* `get_translation_manager()` — get the active manager (raises if unset).
* `has_translation_manager()` — whether a manager is configured.

## Models

Source: [`models.py`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/models.py)

* `TranslationEntry(key, value, variant=None, draft=False)` — one entry.
* `TranslationFile(translations=[...])` — the on-disk file schema.
* `Translation(locale, entries=None)` — in-memory per-locale store, with
  `from_file`, `from_entries`, `get`, `add`, and `entries`.
* `dump_translation_file(entries, path)` — write entries to a JSON file.

## Modules

Source: [`modules.py`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/modules.py)

* `BaseModuleTranslation` — subclass and implement `get_source_dirs` and
  `get_translation_dir`. Optionally implement `get_template_dirs`,
  `get_template_suffixes` and `get_jinja_environment` to have the extraction
  script parse Jinja templates too.
* `DEFAULT_TEMPLATE_SUFFIXES` — the suffixes read when a module does not declare
  its own.
* `has_suffix(path, suffixes) -> bool` — whether a file name ends with one of
  the suffixes, matched on the name so compound ones like `.html.j2` work.

## Extraction

Source: [`extract_translations.py`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/extract_translations.py)

Run it with `python -m fastapi_simple_i18n.extract_translations`. The pieces are
usable on their own:

* `DEFAULT_FUNCTION_NAMES = ("t",)` — the names the Python extractor looks for,
  overridable with `--python-function`.
* `TranslationCallVisitor(source, function_names)` — the `ast` node walker that
  collects the keys. A call matches on the name alone, so `helpers.t("Key")` is
  found like `t("Key")`, and an alias or a wrapper is found when its name is
  listed.
* `extract_from_python_file(path, function_names)` — parse one file.
* `PythonExtractor` — scan directories for `.py` files. `function_names` and
  `suffixes` are class attributes you can override.
* `TemplateExtractor(backend)` — the same for templates, delegating to a
  [`JinjaExtractor`](#templates).
* `build_template_extractor(module, function_names, filter_names)` — build the
  template extractor for a module, reading the environment it declares.

## Templates

Source: [`jinja.py`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/jinja.py)

* `install_translation_support(environment, *, function_name=None, filter_name=None, trans_blocks=True) -> Environment`
  — add `t()`, the `t` filter, `{% trans %}` blocks and the formatters to a Jinja
  environment. `function_name` and `filter_name` accept a name or several names.
* `build_default_environment() -> Environment` — an environment with the helpers
  installed, used by the extraction script as a fallback.
* `get_jinja_config(environment) -> JinjaConfig` — the names installed on an
  environment, or the defaults.
* `JinjaConfig(function_names=("t",), filter_names=("t",), trans_blocks=True)` — the
  names, stored on the environment by the installer.
* `template_translate(context, value, *args, **params) -> LazyTranslation` — the
  callable the installer registers as both the global and the filter. It takes
  the Jinja context so that Jinja never constant-folds a literal call while
  compiling.
* `JinjaExtractor(environment=None, config=None)` — collect `(key, variant)`
  pairs from a template, used by the extraction script. `handles(path)` reports
  whether a file is one of its templates.
* `TemplateCallVisitor(config, source_name, source)` — the node walker that does
  the collecting. A call through an attribute (`i18n.t("Key")`) matches on the
  name after the dot.

## Negotiation

Source: [`negotiation.py`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/negotiation.py)

* `parse_accept_language(header)` — parse into locale codes by quality.
* `negotiate_locale(header, supported, default)` — pick the best locale.

## Middleware

Source: [`middleware.py`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/middleware.py)

* `TranslationMiddleware(app, manager, default_locale="en", builtin_locale="en")`
  — Starlette/FastAPI middleware that registers the manager, sets the default
  locale, and negotiates the request locale.
