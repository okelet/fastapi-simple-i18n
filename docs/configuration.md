# Configuration

## The TranslationManager

The `TranslationManager` is the central registry. Create one, tell it your
built-in locale, and register translations:

```python
from fastapi_simple_i18n.manager import TranslationManager

from myapp.i18n import AppTranslation

manager = TranslationManager(builtin_locale="en")
manager.register_translation(AppTranslation)
```

The `builtin_locale` is the language your source strings are written in. For
that locale, keys are returned unchanged and no translation file is needed.

You can also register translations without a module, which is handy for tests
and scripts:

```python
from fastapi_simple_i18n.models import TranslationEntry

manager.add_entries(
    "es",
    [
        TranslationEntry(key="Yes", value="Sí"),
        TranslationEntry(key="Archive", value="Archivo", variant="noun"),
    ],
)
```

## The active manager

`t()` and the formatting helpers look up a process-wide *active* manager. The
FastAPI middleware sets it for you; in scripts you set it explicitly:

```python
from fastapi_simple_i18n.registry import set_translation_manager

set_translation_manager(manager)
```

## The current locale

The current locale lives in a `ContextVar`, so it is safe across async requests,
threads, and background tasks. Resolution order for `get_current_locale()`:

* The locale forced with `set_current_locale(...)` for the current context.
* Otherwise the process-wide default locale (`set_default_locale(...)`).

```python
from fastapi_simple_i18n.locale import (
    get_current_locale,
    set_current_locale,
    set_default_locale,
)

set_default_locale("en")
set_current_locale("es")
assert get_current_locale() == "es"
```

`set_current_locale` returns a token you can pass to `reset_current_locale` to
restore the previous value. For a scoped change, use the `as_locale` context
manager, which restores the previous locale automatically on exit:

```python
from fastapi_simple_i18n.locale import as_locale

with as_locale("fr"):
    ...  # current locale is "fr" here
# previous locale restored here
```

## Resolution rules

When you translate a key for a target locale:

* If the target locale equals the built-in locale, the key is returned verbatim
  and any variant is ignored.
* Otherwise the `(key, variant)` entry is looked up. Draft entries are used
  as-is.
* If no entry matches, the key itself is returned as a fallback and a warning is
  logged.
