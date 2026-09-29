# Getting started

## Installation

Install directly from GitHub with `uv`:

```bash
uv add "git+https://github.com/okelet/fastapi-simple-i18n"
```

The core package depends only on `babel`. `TranslationMiddleware` is the only
module that needs Starlette, and it ships in the `fastapi` extra:

```bash
uv add "fastapi-simple-i18n[fastapi] @ git+https://github.com/okelet/fastapi-simple-i18n"
```

In a FastAPI project you already have Starlette installed, so the extra is a
no-op; a CLI-only project can skip it. Importing the middleware without
Starlette raises an `ImportError` that says so.

## Your first translation

Create a translation module for your app. It tells the system where your source
code and translation files live:

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

Add a Spanish file at `translations/es.json`:

```json
{
  "translations": [
    { "key": "Hello, {name}!", "value": "¡Hola, {name}!" }
  ]
}
```

Then use it. In FastAPI the middleware wires everything up; in a script you do
it by hand. Both are covered next:

* [Usage in FastAPI](fastapi.md)
* [Usage in CLI scripts](cli.md)
