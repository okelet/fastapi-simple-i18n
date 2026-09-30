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
    python -m examples.cli_app.main --locale es --timezone Europe/Madrid
    python -m examples.cli_app.main --locale fr --timezone Asia/Tokyo
"""

import argparse
from datetime import UTC, datetime

from fastapi_simple_i18n.helpers import t, t_amount, t_date, t_datetime, t_money, t_number
from fastapi_simple_i18n.locale import get_current_locale, set_current_locale, set_default_locale
from fastapi_simple_i18n.manager import TranslationManager
from fastapi_simple_i18n.registry import set_translation_manager
from fastapi_simple_i18n.timezone import get_current_timezone, set_current_timezone, set_default_timezone

from ..fastapi_app.i18n import AppTranslation


def configure_i18n(locale: str, timezone: str = "UTC") -> None:
    """
    Configure the translation manager, current locale, and timezone for the script.

    This is the CLI equivalent of adding :class:`TranslationMiddleware` to a
    FastAPI app: the manager is registered globally, the default locale and
    timezone are applied process-wide, and the requested locale and timezone
    are forced for the current context.
    """
    manager = TranslationManager(builtin_locale="en")
    manager.register_translation(AppTranslation)
    set_translation_manager(manager)
    set_default_locale("en")
    set_default_timezone("UTC")
    set_current_locale(locale)
    set_current_timezone(timezone)


def main() -> None:
    """
    Parse arguments, configure i18n, and print some translated output.
    """
    parser = argparse.ArgumentParser(description="fastapi-simple-i18n CLI example.")
    parser.add_argument("--locale", default="en", help="Locale to render output in (e.g. es, fr).")
    parser.add_argument("--timezone", default="UTC", help="IANA timezone for date/time helpers (e.g. Europe/Madrid, Asia/Tokyo).")
    args = parser.parse_args()

    configure_i18n(args.locale, args.timezone)

    print(f"[locale={get_current_locale()} timezone={get_current_timezone()}]")
    moment = datetime(2026, 8, 30, 14, 30, 0, tzinfo=UTC)
    print(t("Welcome to the example app"))
    print(t("Hello, {name}!", name="Ada"))
    print(t("There are {item_count} items in your cart", item_count=3))
    print(t("Archive", _variant="verb"), "/", t("Archive", _variant="noun"))
    print(t_number(1234567.89))
    print(t_money(1234.5, "EUR"))
    print(t_amount(1234.5))
    print(t_date(moment.date()))
    print(f"{t_datetime(moment)} ({get_current_timezone()})")
    print(f"{t_datetime(moment, tz='UTC')} (UTC)")


if __name__ == "__main__":
    main()
