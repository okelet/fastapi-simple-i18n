"""
Example CLI script using fastapi-simple-i18n without a web server.

Because ``t()`` relies on a globally-configured translation manager and the
current-locale context variable, a CLI script only needs to set both up once at
startup. After that, ``t()`` and the formatting helpers work exactly as they do
inside a FastAPI request.

Run it with::

    python -m examples.cli_app.main --locale es
    python -m examples.cli_app.main --locale fr
    python -m examples.cli_app.main            # built-in locale (en)
"""

import argparse
from datetime import datetime

from fastapi_simple_i18n.helpers import t, t_date, t_number
from fastapi_simple_i18n.locale import set_current_locale, set_default_locale
from fastapi_simple_i18n.manager import TranslationManager
from fastapi_simple_i18n.registry import set_translation_manager

from ..fastapi_app.i18n import AppTranslation


def configure_i18n(locale: str) -> None:
    """
    Configure the translation manager and current locale for the script.

    This is the CLI equivalent of adding :class:`TranslationMiddleware` to a
    FastAPI app.
    """
    manager = TranslationManager(builtin_locale="en")
    manager.register_translation(AppTranslation)
    set_translation_manager(manager)
    set_default_locale("en")
    set_current_locale(locale)


def main() -> None:
    """
    Parse arguments, configure i18n, and print some translated output.
    """
    parser = argparse.ArgumentParser(description="fastapi-simple-i18n CLI example.")
    parser.add_argument("--locale", default="en", help="Locale to render output in (e.g. es, fr).")
    args = parser.parse_args()

    configure_i18n(args.locale)

    print(t("Welcome to the example app"))
    print(t("Hello, {name}!", name="Ada"))
    print(t("There are {item_count} items in your cart", item_count=3))
    print(t("Archive", _variant="verb"), "/", t("Archive", _variant="noun"))
    print(t_number(1234567.89))
    print(t_date(datetime(2026, 8, 30).date()))


if __name__ == "__main__":
    main()
