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

If you need manual control instead, use the token returned by
`set_current_locale` with `reset_current_locale`.
