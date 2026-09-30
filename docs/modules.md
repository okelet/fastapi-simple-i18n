# Modules

A translation *module* lets a package (your app, or a reusable library) ship its
own translatable strings and locale files. It is a class that subclasses
`BaseModuleTranslation` and answers two questions:

* Where is the source code to scan for translatable strings?
* Where are the per-locale JSON files?

## Defining a module

```python
from pathlib import Path

from fastapi_simple_i18n.modules import BaseModuleTranslation


class AppTranslation(BaseModuleTranslation):

    @classmethod
    def get_source_dirs(cls) -> list[Path]:
        return [Path(__file__).parent]

    @classmethod
    def get_translation_dir(cls) -> Path:
        return Path(__file__).parent / "translations"
```

Most modules return the directory of their own package as the single source
dir, but you may return several directories if a module spans more than one.

The translation directory holds one JSON file per locale:

```text
translations/
    es.json
    fr.json
```

A file name is a locale tag, and any spelling of one is accepted (`es`,
`es-ES`, `es_ES`, `ES-es`), because the file name is resolved through the same
entry point as everything else. A file that is *not* named after a locale is
refused with an error naming it, rather than registered as a locale the library
cannot resolve.

## Registering a module

Register a module on the fly with the manager. This loads every locale file it
exposes (skipping the built-in locale):

```python
get_translation_manager().register_translation(MyModuleTranslation)
```

Or at startup, alongside your own app's translations:

```python
manager = TranslationManager(builtin_locale="en")
manager.register_translation(AppTranslation)
manager.register_translation(SomeLibraryTranslation)
```

## Helper methods

`BaseModuleTranslation` provides convenience classmethods:

* `discover_locales()` — returns the sorted locale codes found in the translation
  directory (the JSON file stems), as written on disk.
* `get_translation_file(locale)` — returns the path to a locale's JSON file.

These are also what the extraction script uses to find and update files.

## Template methods

Three more classmethods describe the Jinja templates of a module, all optional
and all used by the extraction script. They do nothing unless you override them,
so a module without templates never needs the `jinja` extra.

* `get_template_dirs()` — directories with templates to scan. Defaults to none.
* `get_template_suffixes()` — which suffixes are templates. Defaults to
  `(".jinja", ".jinja2", ".html", ".html.j2", ".j2.html")`. Suffixes are matched
  against the whole file name, which is what makes the compound ones work:
  `pathlib.Path.suffix` only ever reports the last part of `page.html.j2`.
* `get_jinja_environment()` — the environment used to parse them. Defaults to
  `None`, which makes the extraction script use a plain environment with the
  translation helpers installed.

```python
class AppTranslation(BaseModuleTranslation):

    @classmethod
    def get_template_dirs(cls) -> list[Path]:
        return [Path(__file__).parent / "templates"]

    @classmethod
    def get_jinja_environment(cls) -> Environment:
        return templates.env
```

Returning your real environment is what lets the extraction script see the
names your templates actually use, and any custom delimiters, extensions or
`{% raw %}` blocks. See [Templates](jinja.md) for the details.
