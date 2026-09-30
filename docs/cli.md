# Usage in CLI scripts

`t()` and the formatting helpers do not require a web server. They only need two
things configured once at startup:

* An active `TranslationManager` (via `set_translation_manager`).
* A current locale (via `set_current_locale`), with an optional default.

This is the manual equivalent of what `TranslationMiddleware` does per request.

## Minimal script

```python
from fastapi_simple_i18n.helpers import t
from fastapi_simple_i18n.locale import set_current_locale, set_default_locale
from fastapi_simple_i18n.manager import TranslationManager
from fastapi_simple_i18n.registry import set_translation_manager

from myapp.i18n import AppTranslation


def configure_i18n(locale: str) -> None:
    manager = TranslationManager(builtin_locale="en")
    manager.register_translation(AppTranslation)
    set_translation_manager(manager)
    set_default_locale("en")
    set_current_locale(locale)


configure_i18n("es")
print(t("Hello, {name}!", name="Ada"))
```

## With argparse

```python
import argparse

from fastapi_simple_i18n.helpers import t, t_number

from .cli import configure_i18n  # or wherever you put it


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--locale", default="en")
    args = parser.parse_args()

    configure_i18n(args.locale)

    print(t("Welcome to the example app"))
    print(t_number(1234567.89))


if __name__ == "__main__":
    main()
```

Run it:

```bash
uv run python -m myapp.cli --locale es
uv run python -m myapp.cli --locale fr
uv run python -m myapp.cli            # built-in locale (en)
```

The `--locale` value is a user-facing argument, so treat an unusable one as the
bad input it is. Every setter validates and raises `ValueError`:

```python
from fastapi_simple_i18n.locale import resolve_locale

try:
    locale = resolve_locale(args.locale)
except ValueError as exc:
    parser.error(str(exc))
```

Any spelling of a locale is accepted (`es`, `es-ES`, `es_ES`, `ES-es`), and
`resolve_locale` returns the `babel.core.Locale` you can log or compare:

```python
locale = resolve_locale(args.locale)
print(f"serving {locale} ({locale.language})")
```

## Long-running scripts and tasks

The current locale is stored in a `ContextVar`, so if you spawn tasks or threads
that need a different locale, call `set_current_locale` inside them.

For a scoped, temporary change, prefer the `as_locale` context manager, which
restores the previous locale on exit (even if the block raises):

```python
from fastapi_simple_i18n.locale import as_locale
from fastapi_simple_i18n.helpers import t

with as_locale("es"):
    print(t("Hello, {name}!", name="Ada"))
# the previous locale is restored here
```

The timezone has the same pair of helpers (`as_timezone`,
`set_current_timezone`, `reset_current_timezone`), which `t_time` and
`t_datetime` read. It starts at `UTC` and is always something, so
`get_current_timezone()` never hands you `None` and no formatter silently falls
back to the machine's local zone:

```python
from fastapi_simple_i18n.timezone import as_timezone, get_current_timezone, set_default_timezone

set_default_timezone("Europe/Madrid")   # the whole script

with as_timezone("Asia/Tokyo"):
    get_current_timezone()   # ZoneInfo("Asia/Tokyo")
get_current_timezone()       # ZoneInfo("Europe/Madrid")
```

If a `--timezone` argument is optional, resolve it before passing it, since
every setter refuses `None`:

```python
timezone = args.timezone or DEFAULT_TIMEZONE
set_default_timezone(timezone)
```

If you need manual control instead, use the token returned by
`set_current_locale` with `reset_current_locale`.
