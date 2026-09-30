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
that locale, keys are returned unchanged and no translation file is needed. It
is stored as a `babel.core.Locale`, so any spelling works (`"en"`, `"EN-us"`)
and it never decides whether a translation is found.

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

## Locales

Every locale the library stores is a [`babel.core.Locale`](https://babel.pocoo.org/en/latest/api/core.html#babel.core.Locale),
and every function that takes one accepts any spelling of a tag:

```python
from fastapi_simple_i18n.locale import resolve_locale

resolve_locale("es")            # Locale('es')
resolve_locale("es_ES")         # Locale('es', territory='ES')
resolve_locale("es-ES")         # Locale('es', territory='ES')
resolve_locale("ES-es")         # Locale('es', territory='ES')
resolve_locale("zh_Hans_CN")    # Locale('zh', script='Hans', territory='CN')
```

Because the locale is normalized on the way in, how it was spelled never
changes the result — this is what lets a translation file named `pt-BR.json` be
served to a client that asked for `pt_BR` through an `Accept-Language` header:

```python
manager.add_entries("pt-BR", [TranslationEntry(key="Yes", value="Sim")])
manager.translate("Yes", locale="pt_br")   # "Sim"
```

A locale that is not one is rejected where it is passed, with a message that
says what is wrong with it:

```python
set_default_locale("en_US-POSIX")   # ValueError: ... use a single separator, '_' or '-', not both
set_default_locale("english")       # ValueError: Invalid locale 'english': unknown locale 'english'
set_default_locale("xx_YY")         # ValueError: Invalid locale 'xx_YY': unknown locale 'xx_YY'
```

`get_current_locale()` returns a `Locale`, not a string, so `== "es"` is
`False`. Compare it with another `Locale`, and use `str(...)` where a string is
what you need:

```python
from babel.core import Locale
from fastapi_simple_i18n.locale import get_current_locale

locale = get_current_locale()
locale == Locale("es", territory="ES")   # True, whatever the spelling used
str(locale)                              # "es_ES"
locale.language                          # "es"
locale.territory                         # "ES"
```

## The current locale

The current locale lives in a `ContextVar`, so it is safe across async requests,
threads, and background tasks. Resolution order for `get_current_locale()`:

* The locale forced with `set_current_locale(...)` for the current context.
* Otherwise the process-wide default locale (`set_default_locale(...)`).

```python
from fastapi_simple_i18n.locale import (
    get_current_locale,
    resolve_locale,
    set_current_locale,
    set_default_locale,
)

set_default_locale("en")
set_current_locale("es")
assert get_current_locale() == resolve_locale("es")
```

`set_current_locale` returns a token you can pass to `reset_current_locale` to
restore the previous value. For a scoped change, use the `as_locale` context
manager, which restores the previous locale automatically on exit:

```python
from fastapi_simple_i18n.locale import as_locale

with as_locale("fr"):
    ...  # current locale is fr here
# previous locale restored here
```

## The current timezone

The timezone works the same way, in its own `ContextVar`, and is used by
`t_time`, `t_datetime` and their lazy counterparts. There is always one: it
starts at `UTC` and is never absent, so `get_current_timezone()` always returns a
real `tzinfo` and a naive datetime is always read in a known zone.

```python
from fastapi_simple_i18n.timezone import as_timezone, get_current_timezone

get_current_timezone()                 # ZoneInfo("UTC")

with as_timezone("Europe/Madrid"):
    get_current_timezone()             # ZoneInfo("Europe/Madrid")
get_current_timezone()                 # ZoneInfo("UTC")
```

Because there is always a timezone, every function that takes one refuses
`None` — `set_current_timezone`, `set_default_timezone` and `as_timezone`
included. A bad name is reported where it was written, never surfacing later as
a moment in the wrong zone:

```python
set_default_timezone("Europe/Madrid")   # fine
set_default_timezone("Not/A_Zone")      # ZoneInfoNotFoundError
set_current_timezone(None)              # TypeError: Invalid timezone None
set_default_timezone("Europe/Madrid")   # process-wide, for the whole app
```

To render one value in a different zone without touching the context, pass
`tz=` to the helper:

```python
t_datetime(moment)                      # in the active timezone
t_datetime(moment, tz="Asia/Tokyo")     # in Tokyo, for this call only
```

## Resolution rules

When you translate a key for a target locale:

* If the target locale equals the built-in locale, the key is returned verbatim
  and any variant is ignored.
* Otherwise the `(key, variant)` entry is looked up. Draft entries are used
  as-is.
* If no entry matches, the key itself is returned as a fallback and a warning is
  logged.
