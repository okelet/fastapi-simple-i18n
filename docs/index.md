# fastapi-simple-i18n

Simple, module-friendly internationalization for FastAPI apps and CLI scripts.

`fastapi-simple-i18n` gives you a small, explicit translation system:

* A `TranslationManager` that holds your translations and resolves keys.
* JSON translation files with support for **variants** and **drafts**.
* Locales as `babel.core.Locale` objects, accepted and validated in any
  spelling, so how a locale is written never changes the result.
* **Eager** translations (`t()`) and **lazy** ones (`lazy_t()`) that resolve at
  render time, honoring the active locale.
* A locale `ContextVar` with `set_current_locale` / `get_current_locale`, and a
  matching timezone one, always present and defaulting to `UTC`.
* FastAPI middleware that negotiates the locale from `Accept-Language`.
* Babel helpers for locale-aware numbers, amounts, dates, and times.
* Registrable translation **modules** so libraries can ship their own strings.
* An AST-based extraction script to keep locale files in sync with the code.
* A translation file web UI (FastAPI + HTMX + Alpine) that browses and edits
  the locale JSON files directly. Its dependencies ship in the `web`
  dependency group.

## Design at a glance

The system revolves around four ideas:

* A **source string** (the `key`) is written in the application's *built-in*
  language. For the built-in locale, keys are returned verbatim, so no file is
  needed.
* Each other locale has a JSON file of entries mapping `key` (plus optional
  `variant`) to a translated `value`.
* A **locale** is a `babel.core.Locale` everywhere inside the library. It is
  resolved and validated the moment it enters — from a query parameter, a
  header, a file name, a CLI argument — so `es`, `es_ES`, `es-ES` and `ES-es` are
  the same locale and an unusable one is a `ValueError` where it was written,
  not a missing translation much later. `get_current_locale()` returns one;
  wrap it in `str(...)` where a string is what you need (a JSON payload), and
  read `.language` / `.territory` where a subtag is.
* At runtime, `t("...")` returns a `TranslatableStr`, a `str` subclass
  carrying the translated text. The lookup happens against the locale that is
  active at call time, so the result is a real `str` and works in any string
  context (`json.dumps`, Pydantic str fields, `urllib.parse.quote`, `| tojson`,
  concatenation) with no `str()` wrapper. `lazy_t(...)` is the lazy counterpart:
  it returns a `LazyTranslatableStr` (NOT a `str` subclass) that defers the
  lookup until render, so the same captured value can render in different
  locales at different times — at the cost of needing an explicit `str()`
  wrapper at string-protocol boundaries. In Jinja templates the lazy variant
  works out of the box because `install_translation_support` registers
  `lazy_t` / `lazy_t_number` / `lazy_t_money` / `lazy_t_amount` / `lazy_t_date` /
  `lazy_t_time` / `lazy_t_datetime` and Jinja's default `finalize` already calls
  `str()` on every output value, so `{{ lazy_t("Key") }}` renders correctly
  without any wrapper.

Continue with [Getting started](getting-started.md).

## Development note

This code was developed mostly with AI (vibe coding), but has been reviewed and
validated by a human.
