# API reference

This page summarizes the public API. Import each symbol from its submodule (the
top-level `fastapi_simple_i18n` package deliberately re-exports nothing):

* [`fastapi_simple_i18n.locale`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/locale.py) — `resolve_locale`, `get_current_locale`, `set_current_locale`, `reset_current_locale`, `as_locale`, `get_default_locale`, `set_default_locale`, `current_locale`
* [`fastapi_simple_i18n.timezone`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/timezone.py) — `resolve_timezone`, `get_current_timezone`, `set_current_timezone`, `reset_current_timezone`, `as_timezone`, `get_default_timezone`, `set_default_timezone`, `current_timezone`, `DEFAULT_TIMEZONE`
* [`fastapi_simple_i18n.helpers`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/helpers.py) — `t`, `t_number`, `t_money`, `t_amount`, `t_date`, `t_time`, `t_datetime`, `lazy_t`, `lazy_t_number`, `lazy_t_money`, `lazy_t_amount`, `lazy_t_date`, `lazy_t_time`, `lazy_t_datetime`, `TranslatableStr`, `LazyTranslatableStr`, `LazyNumber`, `LazyMoney`, `LazyAmount`, `LazyDate`, `LazyTime`, `LazyDateTime`, `MONEY_FORMAT`
* [`fastapi_simple_i18n.manager`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/manager.py) — `TranslationManager`
* [`fastapi_simple_i18n.middleware`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/middleware.py) — `TranslationMiddleware`
* [`fastapi_simple_i18n.models`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/models.py) — `Translation`, `TranslationEntry`, `TranslationFile`, `TranslationFormatError`, `dump_translation_file`
* [`fastapi_simple_i18n.modules`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/modules.py) — `BaseModuleTranslation`
* [`fastapi_simple_i18n.registry`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/registry.py) — `get_translation_manager`, `set_translation_manager`, `has_translation_manager`
* [`fastapi_simple_i18n.negotiation`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/negotiation.py) — `parse_accept_language`, `negotiate_locale`
* [`fastapi_simple_i18n.jinja`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/jinja.py) — `install_translation_support`, `build_default_environment`, `get_jinja_config`, `JinjaConfig`, `JinjaExtractor`, `TemplateCallVisitor`, `CONTEXT_HELPERS`, `LAZY_FORMATTERS`
* [`fastapi_simple_i18n.extract_translations`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/extract_translations.py) — the extraction script: `TranslationCallVisitor`, `extract_from_python_file`, `PythonExtractor`, `TemplateExtractor`, `build_template_extractor`, `merge_keys_into_translation`, `resolve_module`, `run`, `main`

Only `fastapi_simple_i18n.middleware` needs Starlette
(`fastapi-simple-i18n[fastapi]`); importing it without Starlette raises an
`ImportError` that says which extra to install. Only `fastapi_simple_i18n.jinja`
needs Jinja2 (`fastapi-simple-i18n[jinja]`), and importing it without Jinja2
raises the same kind of `ImportError`.

## Locales are `babel.core.Locale` objects

Every locale the library stores, returns or accepts is a
[`babel.core.Locale`](https://babel.pocoo.org/en/latest/api/core.html#babel.core.Locale).
`get_current_locale()` returns one, `TranslationManager.supported_locales()`
returns a set of them, `Translation.locale` is one, and `negotiate_locale()`
returns one.

They are not strings, so `get_current_locale() == "es"` is `False`; compare
against another `Locale` (`resolve_locale("es")`) or convert with `str(...)`
where a string is what you need (a JSON payload, a file name, a log message).
What the object gives you in return is the subtags and the display name:

```python
from fastapi_simple_i18n.locale import get_current_locale

locale = get_current_locale()
str(locale)              # "es_ES"
locale.language          # "es"
locale.territory         # "ES"
locale.script            # None (or "Hans", "Latn", ...)
locale.get_display_name()  # "español (España)"
```

## Locale resolution

Source: [`locale.py`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/locale.py)

* `resolve_locale(locale) -> Locale` — the single entry point that turns a locale
  written anywhere (query parameter, `Accept-Language` header, JSON file name,
  CLI argument) into a validated `Locale`. Accepts a `Locale` (returned
  as-is) or a tag in any spelling: `es`, `es_ES`, `es-ES`, `ES-es`, `zh_Hans_CN`,
  `en_US_POSIX`, with surrounding blanks. Raises `ValueError` for an empty value,
  a tag mixing both separators (`en_US-POSIX`), a malformed tag (`english`,
  `en--US`) and a locale CLDR does not know (`xx_YY`).
* `get_current_locale() -> Locale` — the effective locale (the value set for
  this context, else the process default). Never `None`.
* `set_current_locale(locale) -> Token` — force the locale for the current
  context; returns a token. Validates.
* `reset_current_locale(token)` — restore the previous locale.
* `as_locale(locale) -> ContextManager[Locale]` — force `locale` for a `with`
  block and restore the previous value on exit (even on exceptions). Yields the
  resolved locale.
* `get_default_locale() -> Locale` / `set_default_locale(locale)` — the
  process-wide default. Validates.
* `current_locale` — the underlying `ContextVar[Locale | None]`; `None` means
  "not resolved in this context".

Every function that takes a locale raises `ValueError` rather than storing or
propagating an unusable one, so a typo fails where it is written:

```python
from fastapi_simple_i18n.locale import set_current_locale

set_current_locale("es-ES")   # fine
set_current_locale("es-ES")   # fine
set_current_locale("en_US-POSIX")  # ValueError: Invalid locale 'en_US-POSIX': use a single separator, ...
set_current_locale("english")    # ValueError: Invalid locale 'english': unknown locale 'english'
```

## Timezone context

Source: [`timezone.py`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/timezone.py)

There is always a timezone in effect. `get_current_timezone()` answers with a
real `tzinfo` from the very first call, and every function that *takes* a
timezone refuses `None`, so "no timezone" is not a state the library can be in.
The alternative — falling back to the process local zone — would make a
rendered moment depend on where the server happens to run.

* `DEFAULT_TIMEZONE` — the `ZoneInfo("UTC")` the library starts in, and what
  `default_timezone` defaults to.
* `resolve_timezone(timezone) -> tzinfo` — a `tzinfo` instance (returned as-is)
  or an IANA name (`"Europe/Madrid"`, `"UTC"`), with surrounding blanks
  stripped. Raises `TypeError` for anything that is neither, `ValueError` for a
  blank name, and `ZoneInfoNotFoundError` for a name CLDR's zone database does
  not know.
* `get_current_timezone() -> tzinfo` — the effective timezone (the value set
  for this context, else the process default). Never `None`.
* `set_current_timezone(timezone) -> Token` / `reset_current_timezone(token)`.
  Both validate; there is no way to clear the override.
* `as_timezone(timezone) -> ContextManager[tzinfo]` — force `timezone` for a
  `with` block, validate on entry, restore the previous value on exit. Yields
  the resolved `tzinfo`, so `with as_timezone("UTC") as tz:` works.
* `get_default_timezone() -> tzinfo` / `set_default_timezone(timezone)` — the
  process-wide default. It starts at `DEFAULT_TIMEZONE` and can be changed but
  never unset.
* `current_timezone` — the underlying `ContextVar[tzinfo | None]`. The `None` is
  the internal "nothing was resolved for this context" marker that makes
  `reset_current_timezone` and the per-request reset work; it is never what a
  caller reads.

```python
from fastapi_simple_i18n.timezone import get_current_timezone

get_current_timezone()               # ZoneInfo("UTC")
str(get_current_timezone())          # "UTC"
```

## Translation helpers

Source: [`helpers.py`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/helpers.py)

Every helper that takes a `locale` argument accepts a locale tag, an existing
`Locale`, or `None` for "whichever locale is active right now", and validates a
tag the moment it is passed.

`t(key, _variant=None, **params) -> TranslatableStr`

Eager. Return a `str` subclass carrying the translated text. The lookup
happens at call time against the locale that is active then, and `**params`
are applied via `str.format`. Because the return value *is* a `str`, it
works anywhere a string is expected (`json.dumps`, Pydantic str fields,
`urllib.parse.quote`, concatenation, `| tojson` in Jinja) without an
explicit `str()` wrapper. Use `_variant` to select a variant.

`t_number(value, format="#,##0.###", locale=None) -> str`

Eager. Format a number for the current (or given) locale.

`t_money(value, currency="", locale=None) -> str`

Eager. Format a monetary amount with its currency symbol. `currency` is an ISO
code, case-insensitive (`"EUR"`, `"usd"`). A blank or unrecognised code
degrades to a plain localized decimal (two decimals) and logs a warning, so a
mistyped currency never breaks a rendered page.

`t_amount(value, format="#,##0.00", locale=None) -> str`

Eager. Format a plain decimal with no currency symbol, for sums that mix
currencies. The default `MONEY_FORMAT` always shows two decimals, unlike
`t_number`.

`t_date(value, format="medium", locale=None) -> str`

Eager. Format a date. `format` is `"short"`, `"medium"`, `"long"`, `"full"`,
or a Babel pattern.

`t_time(value, format="short", locale=None, tz=None) -> str`

Eager. Format a time. `tz` is applied to `datetime` values (a naive `time` is
shown as-is, since `time` has no date to project onto a zone). `tz=None` means
"whichever timezone is active", which is always a concrete zone.

`t_datetime(value, format="medium", locale=None, tz=None) -> str`

Eager. Format a datetime, projected onto `tz` first. `tz=None` means "whichever
timezone is active" (UTC until something is configured), never "the process
local zone". A `tz=` value is resolved on every call, so an unknown IANA name
raises `ZoneInfoNotFoundError` there.

`lazy_t(key, _variant=None, **params) -> LazyTranslatableStr`

Lazy. Return a string-like wrapper that resolves to the translated text
when read, against the locale that is active *then*. NOT a `str`
subclass — operations that bypass Python's dunder protocol
(`json.dumps`, `str.encode`, Pydantic str fields, `| tojson` in Jinja)
need an explicit `str()` wrapper at the boundary.

Use `lazy_t` when the value is captured at a point where the locale is not
yet known (a module-level constant, a decorator that runs before the
request, a pre-built message rendered from a different context) and must
track whichever locale is active later.

`lazy_t_number(value, format="#,##0.###", locale=None) -> LazyNumber`

Lazy counterpart of `t_number`. The format is applied on every read, so
the same value can render in different locales at different times.

`lazy_t_money(value, currency="", locale=None) -> LazyMoney`

Lazy counterpart of `t_money`, with the same fallback contract: a blank or
unrecognised currency renders a plain localized decimal.

`lazy_t_amount(value, format="#,##0.00", locale=None) -> LazyAmount`

Lazy counterpart of `t_amount`.

`lazy_t_date(value, format="medium", locale=None) -> LazyDate`

Lazy counterpart of `t_date`.

`lazy_t_time(value, format="short", locale=None, tz=None) -> LazyTime`

Lazy counterpart of `t_time`.

`lazy_t_datetime(value, format="medium", locale=None, tz=None) -> LazyDateTime`

Lazy counterpart of `t_datetime`.

An explicit `locale` (or `tz`) on a lazy formatter is validated when the object
is built, not when it is read, so a mistyped value is reported at the line that
made the mistake.

## TranslatableStr

Source: [`helpers.py`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/helpers.py)

The `str` subclass returned by `t()`. Defined as a subclass (and not
aliased to `str`) so introspection and tests can still tell translated
strings apart when needed.

## LazyTranslatableStr / LazyNumber / LazyMoney / LazyAmount / LazyDate / LazyTime / LazyDateTime

Source: [`helpers.py`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/helpers.py)

String-like wrappers returned by `lazy_t` and the lazy formatters. NOT
`str` subclasses. Each one stores the value (and the format / variant
where applicable) and resolves to a fresh `str` every time it is read,
through `__str__`, `__format__`, `__add__`, `__radd__`, `__mul__`,
`__mod__`, `__eq__`, `__ne__`, `__hash__`, `__contains__`, `__len__`,
`__getitem__` and `__iter__`. Comparing, hashing and formatting always
go through the resolved string.

The trade-off vs the eager helpers: a lazy value can re-render in a
different locale at a different time, but you must wrap with `str()` at
any boundary that goes through the C-level str protocol (`json.dumps`,
`urllib.parse.quote`, Pydantic str fields, `| tojson` in Jinja).

## TranslationManager

Source: [`manager.py`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/manager.py)

* `TranslationManager(builtin_locale="en")` — create a manager.
* `builtin_locale` — the language the source strings are written in, stored as
  a `Locale`; assigning resolves and validates it.
* `register_translation(module)` — load all locales exposed by a
  `BaseModuleTranslation` subclass. A file not named after a locale is refused.
* `add_translation(translation)` — register/merge a `Translation`.
* `add_entries(locale, entries)` — register a list of `TranslationEntry`.
* `get_translation(locale) -> Translation | None` — the `Translation` for a
  locale, if any.
* `supported_locales() -> set[Locale]` — the set of locales served (includes the
  built-in one).
* `translate(key, variant=None, locale=None) -> str` — resolve a key to a
  string. `None` means the built-in locale.

Translations are keyed by the resolved locale, so how a locale was spelled
never decides whether a translation is found:

```python
manager.add_entries("pt-BR", [TranslationEntry(key="Yes", value="Sim")])
manager.translate("Yes", locale="pt_br")   # "Sim"
manager.translate("Yes", locale="PT-br")   # "Sim"
```

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
  `from_file`, `from_entries`, `get`, `add`, and `entries`. `locale` accepts any
  spelling (or a `Locale`) and is stored resolved as `translation.locale`.
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
* `_locales_to_update(module, extra_locales)` — the `(file stem, locale)` pairs
  a run will write. Every locale is resolved, so an unusable one ends the run
  with a message before anything is written; the file keeps the spelling it was
  given, because that is the name a translator sees in git and in the UI.

## Templates

Source: [`jinja.py`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/jinja.py)

* `install_translation_support(environment, *, function_name=None, filter_name=None, lazy_function_name=None, lazy_filter_name=None, trans_blocks=True) -> Environment`
  — add `t()` / `lazy_t()` (each as a global and a filter), the eager and lazy
  formatters (`t_number` / `lazy_t_number`, `t_money` / `lazy_t_money`,
  `t_amount` / `lazy_t_amount`, `t_date` / `lazy_t_date`, …), the
  `get_current_locale()` and `get_current_tz()` globals, and `{% trans %}`
  blocks to a Jinja environment. Each `*_name` argument accepts a single name
  or a sequence. Jinja's default `finalize` already calls `str()` on every
  output value, so `{{ lazy_t("Key") }}` and `{{ lazy_t_number(1234.5) }}`
  render correctly inside `{{ }}` without any wrapper — only `| tojson` and
  other C-level str consumers still need an explicit `str()` at the boundary.
* `CONTEXT_HELPERS` — the two read-only context globals,
  `get_current_locale` (returns the `Locale`) and `get_current_tz` (returns the
  `tzinfo`, never `None`). Installed with `setdefault`, so an environment that
  already defines one of those names keeps its own.
* `LAZY_FORMATTERS` — the lazy formatter globals, also installed with
  `setdefault`.
* `build_default_environment() -> Environment` — an environment with the helpers
  installed, used by the extraction script as a fallback.
* `get_jinja_config(environment) -> JinjaConfig` — the names installed on an
  environment, or the defaults.
* `JinjaConfig(function_names=("t",), filter_names=("t",), lazy_function_names=("lazy_t",), lazy_filter_names=("lazy_t",), trans_blocks=True)`
  — the names, stored on the environment by the installer.
* `template_translate(context, value, *args, **params) -> TranslatableStr` —
  the callable the installer registers as the eager `t` global and filter. It
  takes the Jinja context so that Jinja never constant-folds a literal call
  while compiling.
* `template_lazy_translate(context, value, *args, **params) -> LazyTranslatableStr`
  — the same shape, but installed as the lazy `lazy_t` global and filter.
  Returns a `LazyTranslatableStr` that resolves at render time via Jinja's
  `finalize` (which calls `str()` on the output value).
* `JinjaExtractor(environment=None, config=None)` — collect `(key, variant)`
  pairs from a template, used by the extraction script. `handles(path)` reports
  whether a file is one of its templates.
* `TemplateCallVisitor(config, source_name, source)` — the node walker that does
  the collecting. A call through an attribute (`i18n.t("Key")`) matches on the
  name after the dot.

## Negotiation

Source: [`negotiation.py`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/negotiation.py)

* `parse_accept_language(header) -> list[str]` — parse into locale codes by
  quality, exactly as they were written.
* `negotiate_locale(header, supported, default) -> Locale` — pick the best
  locale, ignoring spelling. A candidate matches a supported locale exactly, or
  its base language when a supported locale *is* that bare language (`es-ES`
  selects a supported `es`, never a supported `es-MX`). Entries that are not
  locales (`*`, `en-*`, a typo) are skipped; the default is returned when nothing
  matches.

## Middleware

Source: [`middleware.py`](https://github.com/okelet/fastapi-simple-i18n/blob/main/src/fastapi_simple_i18n/middleware.py)

* `TranslationMiddleware(app, manager, default_locale="en", builtin_locale="en", default_timezone=DEFAULT_TIMEZONE, locale_resolver=None, timezone_resolver=None)`
  — pure ASGI middleware that registers the manager, applies the default locale
  and timezone, and resolves the per-request locale from `Accept-Language`
  (or from a `locale_resolver`) and the timezone from a `timezone_resolver`. All
  locale arguments accept any spelling and are validated; `default_timezone` is
  resolved at construction like the locales, so a bad one is reported when the
  middleware stack is built rather than on the first request. A
  `timezone_resolver` returning `None` keeps the default.
