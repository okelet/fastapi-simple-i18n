# fastapi-simple-i18n

Simple, module-friendly internationalization for FastAPI apps and CLI scripts.

`fastapi-simple-i18n` gives you a small, explicit translation system:

* A `TranslationManager` that holds your translations and resolves keys.
* JSON translation files with support for **variants** and **drafts**.
* **Lazy** translations that resolve at render time, honoring the active locale.
* A locale `ContextVar` with `set_current_locale` / `get_current_locale`.
* FastAPI middleware that negotiates the locale from `Accept-Language`.
* Babel helpers for locale-aware numbers, dates, and times.
* Registrable translation **modules** so libraries can ship their own strings.
* An AST-based extraction script to keep locale files in sync with the code.
* A translation file web UI (FastAPI + HTMX + Alpine) that browses and edits
  the locale JSON files directly. Its dependencies ship in the `web`
  dependency group.

## Design at a glance

The system revolves around three ideas:

* A **source string** (the `key`) is written in the application's *built-in*
  language. For the built-in locale, keys are returned verbatim, so no file is
  needed.
* Each other locale has a JSON file of entries mapping `key` (plus optional
  `variant`) to a translated `value`.
* At runtime, `t("...")` returns a `LazyTranslation`. It resolves to a string
  only when converted with `str()`, reading whatever locale is active then.

Continue with [Getting started](getting-started.md).

## Development note

This code was developed mostly with AI (vibe coding), but has been reviewed and
validated by a human.
