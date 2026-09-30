"""
Tests for the Jinja2 integration.
"""

import json
from datetime import date, datetime

import pytest
from babel.core import Locale
from jinja2 import Environment
from jinja2.ext import InternationalizationExtension
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.routing import Route
from starlette.templating import Jinja2Templates
from starlette.testclient import TestClient

from fastapi_simple_i18n.helpers import lazy_t
from fastapi_simple_i18n.jinja import (
    JinjaConfig,
    build_default_environment,
    get_jinja_config,
    install_translation_support,
)
from fastapi_simple_i18n.locale import get_current_locale, set_current_locale
from fastapi_simple_i18n.manager import TranslationManager
from fastapi_simple_i18n.middleware import TranslationMiddleware
from fastapi_simple_i18n.models import TranslationEntry
from fastapi_simple_i18n.timezone import set_current_timezone


def build_manager(manager: TranslationManager) -> None:
    """
    Register the Spanish and French entries used by the template tests.
    """
    manager.add_entries(
        "fr",
        [
            TranslationEntry(key="Hello, {name}!", value="Bonjour, {name} !"),
            TranslationEntry(key="Archive", value="Archiver", variant="verb"),
            TranslationEntry(key="Archive", value="Archive", variant="noun"),
            TranslationEntry(key="Inbox", value="Boîte de réception"),
            TranslationEntry(key="There are %(n)s messages", value="Il y a %(n)s messages"),
        ],
    )
    manager.add_entries(
        "es",
        [
            TranslationEntry(key="Hello, {name}!", value="¡Hola, {name}!"),
            TranslationEntry(key="Inbox", value="Bandeja de entrada"),
        ],
    )


@pytest.fixture(name="env")
def env_fixture(manager: TranslationManager) -> Environment:
    """
    Return an environment with the helpers installed and a populated manager.
    """
    build_manager(manager)
    return install_translation_support(Environment(autoescape=True))


def test_function_resolves_at_render_time(env: Environment, manager: TranslationManager):
    """
    The locale is read when the template renders, not when it is compiled.

    This is a regression test: Jinja constant-folds a filter call with literal
    arguments at compile time, so the callable must take the context or a cached
    template would keep the locale of whoever compiled it first.
    """
    template = env.from_string('{{ t("Hello, {name}!", name="Ada") }}')

    set_current_locale("fr")
    assert template.render() == "Bonjour, Ada !"
    set_current_locale("es")
    assert template.render() == "¡Hola, Ada!"
    set_current_locale("en")
    assert template.render() == "Hello, Ada!"


def test_filter_resolves_at_render_time(env: Environment):
    """
    The filter form reads the locale at render time too.
    """
    template = env.from_string('{{ "Hello, {name}!" | t(name="Ada") }}')

    set_current_locale("fr")
    assert template.render() == "Bonjour, Ada !"
    set_current_locale("en")
    assert template.render() == "Hello, Ada!"


def test_filter_accepts_variant_keyword_and_positional(env: Environment):
    """
    The filter takes the variant as a keyword, as an alias, or positionally.
    """
    set_current_locale("fr")
    assert env.from_string('{{ "Archive" | t(variant="verb") }}').render() == "Archiver"
    assert env.from_string('{{ "Archive" | t(_variant="noun") }}').render() == "Archive"
    assert env.from_string('{{ "Archive" | t("verb") }}').render() == "Archiver"


def test_filter_rejects_more_than_one_positional_argument(env: Environment):
    """
    Only the variant may be positional.
    """
    with pytest.raises(TypeError, match="at most one positional argument"):
        env.from_string('{{ "Archive" | t("verb", "extra") }}').render()


def test_empty_name_sequence_is_rejected():
    """
    Configuring an empty list of names is a mistake worth reporting.
    """
    with pytest.raises(ValueError, match="At least one name"):
        install_translation_support(Environment(), function_name=[])


def test_trans_block_and_context_variant(env: Environment):
    """
    {% trans %} blocks are served by the manager, and a context is a variant.
    """
    set_current_locale("fr")
    assert env.from_string("{% trans %}Inbox{% endtrans %}").render() == "Boîte de réception"
    assert env.from_string('{% trans "verb" %}Archive{% endtrans %}').render() == "Archiver"
    assert env.from_string('{% trans "noun" %}Archive{% endtrans %}').render() == "Archive"


def test_trans_block_interpolates_with_percent_syntax(env: Environment):
    """
    {% trans %} uses %(name)s interpolation, not {name}.
    """
    set_current_locale("fr")
    rendered = env.from_string("{% trans count=n %}There are {{ n }} messages{% endtrans %}").render(n=3)
    assert rendered == "Il y a 3 messages"


def test_pluralize_is_not_supported(env: Environment):
    """
    {% pluralize %} fails with a message that says what to do instead.
    """
    with pytest.raises(NotImplementedError, match="Pluralization is not supported"):
        env.from_string("{% trans count=n %}{{ n }} item{% pluralize %}{{ n }} items{% endtrans %}").render(n=2)


def test_trans_blocks_can_be_disabled(manager: TranslationManager):
    """
    With trans_blocks=False the gettext globals are left untouched.
    """
    build_manager(manager)
    environment = Environment(extensions=[InternationalizationExtension])
    environment.install_null_translations()  # pylint: disable=no-member
    null_gettext = environment.globals["gettext"]

    install_translation_support(environment, trans_blocks=False)

    assert environment.globals["gettext"] is null_gettext
    assert "t" in environment.globals


def test_names_are_configurable(manager: TranslationManager):
    """
    The global and the filter can be renamed, including to several names.
    """
    build_manager(manager)
    environment = install_translation_support(
        Environment(),
        function_name=("translate", "tx"),
        filter_name="trans",
    )

    assert get_jinja_config(environment) == JinjaConfig(function_names=("translate", "tx"), filter_names=("trans",))
    set_current_locale("fr")
    assert environment.from_string('{{ translate("Inbox") }}').render() == "Boîte de réception"
    assert environment.from_string('{{ tx("Inbox") }}').render() == "Boîte de réception"
    assert environment.from_string('{{ "Inbox" | trans }}').render() == "Boîte de réception"
    assert "t" not in environment.globals


def test_get_jinja_config_defaults_to_the_standard_names():
    """
    An environment nobody installed into reports the default names.
    """
    assert get_jinja_config(Environment()) == JinjaConfig()


def test_reinstalling_updates_the_configuration(manager: TranslationManager):
    """
    A second installation with different names takes effect.

    ``Environment.extend()`` ignores attributes that already exist, so storing
    the configuration with it would silently keep the names of the first call.
    """
    environment = build_default_environment()
    assert get_jinja_config(environment).function_names == ("t",)

    install_translation_support(environment, function_name="translate")

    assert get_jinja_config(environment).function_names == ("translate",)
    set_current_locale("es")
    assert environment.from_string('{{ translate("Yes") }}').render() == "Sí"

    install_translation_support(environment)

    assert get_jinja_config(environment).function_names == ("t",)
    assert environment.from_string('{{ t("Yes") }}').render() == "Sí"


def test_formatters_are_registered(manager: TranslationManager):
    """
    The number and date helpers are available to templates.
    """
    build_manager(manager)
    environment = build_default_environment()
    set_current_locale("fr")
    assert environment.from_string("{{ t_number(1234.5) }}").render() == "1\u202f234,5"


def test_money_formatters_are_registered(manager: TranslationManager):
    """
    The money helpers are available to templates, eager and lazy alike.
    """
    build_manager(manager)
    environment = build_default_environment()
    set_current_locale("en")
    assert environment.from_string('{{ t_money(1234.5, "EUR") }}').render() == "€1,234.50"
    assert environment.from_string("{{ t_amount(1234.5) }}").render() == "1,234.50"
    assert environment.from_string('{{ lazy_t_money(1234.5, "EUR") }}').render() == "€1,234.50"
    assert environment.from_string("{{ lazy_t_amount(1234.5) }}").render() == "1,234.50"


def test_get_current_locale_is_available_in_templates(manager: TranslationManager):
    """
    ``get_current_locale()`` gives templates the resolved locale, subtags included.
    """
    build_manager(manager)
    environment = build_default_environment()
    template = environment.from_string("{{ get_current_locale().language }} / {{ get_current_locale().territory }} / {{ get_current_locale() }}")

    set_current_locale("es-ES")
    assert template.render() == "es / ES / es_ES"
    set_current_locale("fr")
    assert template.render() == "fr / None / fr"


def test_get_current_tz_is_available_in_templates(manager: TranslationManager):
    """
    ``get_current_tz()`` gives templates the active timezone, which is never nothing.
    """
    build_manager(manager)
    environment = build_default_environment()
    template = environment.from_string("{{ get_current_tz() }}")

    assert template.render() == "UTC"
    set_current_timezone("Europe/Madrid")
    assert template.render() == "Europe/Madrid"


def test_context_helpers_do_not_overwrite_existing_globals(manager: TranslationManager):
    """
    An environment that already defines one of those names keeps its own.

    The context helpers are installed with ``setdefault``, exactly like the
    formatters: they are conveniences, not something an application has to
    hand over.
    """
    build_manager(manager)
    environment = Environment()
    environment.globals["get_current_locale"] = lambda: "mine"

    install_translation_support(environment)

    assert environment.from_string("{{ get_current_locale() }}").render() == "mine"


def test_lazy_t_global_resolves_at_render_time(env: Environment):
    """
    ``{{ lazy_t("Key") }}`` resolves at render time without a ``| string`` wrapper.

    Jinja's default render pipeline calls ``str()`` on every output value
    (the default ``finalize``), so the lazy wrapper's ``__str__`` is invoked
    at render time and produces the translated text.
    """
    template = env.from_string('{{ lazy_t("Hello, {name}!", name="Ada") }}')

    set_current_locale("fr")
    assert template.render() == "Bonjour, Ada !"
    set_current_locale("en")
    assert template.render() == "Hello, Ada!"


def test_lazy_t_filter_resolves_at_render_time(env: Environment):
    """
    The lazy filter form reads the locale at render time too.
    """
    template = env.from_string('{{ "Hello, {name}!" | lazy_t(name="Ada") }}')

    set_current_locale("fr")
    assert template.render() == "Bonjour, Ada !"
    set_current_locale("en")
    assert template.render() == "Hello, Ada!"


def test_lazy_t_variants_in_templates(env: Environment):
    """
    The lazy template helper honours the ``variant=`` keyword alias.
    """
    set_current_locale("fr")
    assert env.from_string('{{ "Archive" | lazy_t(variant="verb") }}').render() == "Archiver"
    assert env.from_string('{{ "Archive" | lazy_t(variant="noun") }}').render() == "Archive"


def test_lazy_formatters_are_registered(manager: TranslationManager):
    """
    The lazy number and date helpers are available to templates.
    """
    build_manager(manager)
    environment = build_default_environment()
    set_current_locale("fr")
    # No | string needed because Jinja's finalize calls str() on the output.
    assert environment.from_string("{{ lazy_t_number(1234.5) }}").render() == "1\u202f234,5"


def test_lazy_t_needs_str_at_tojson_boundary(env: Environment):
    """
    ``| tojson`` bypasses Jinja's finalize, so the lazy value still needs ``str()`` at that boundary.

    This documents the one place the ``| string`` wrapper is still required:
    anywhere that hands the value to a consumer which reads the C-level
    str buffer directly (``json.dumps``, Pydantic str fields,
    ``urllib.parse.quote``). The renderer output itself IS a real str,
    so json.dumps on the rendered string works.
    """
    set_current_locale("fr")
    rendered = env.from_string('{{ lazy_t("Hello, {name}!", name="Ada") }}').render()
    assert json.dumps(rendered) == '"Bonjour, Ada !"'

    with pytest.raises(TypeError, match="JSON serializable"):
        json.dumps(lazy_t("Hello, {name}!", name="Ada"))


def test_autoescape_escapes_the_resolved_value(env: Environment):
    """
    With autoescape on, the value and the translation are both escaped.
    """
    set_current_locale("es")
    assert env.from_string('{{ t("Hello, {name}!", name=who) }}').render(who="<b>Ada</b>") == "¡Hola, &lt;b&gt;Ada&lt;/b&gt;!"


def test_without_a_manager_it_fails_loudly():
    """
    Using a template translation with no manager configured raises.
    """
    environment = build_default_environment()
    with pytest.raises(RuntimeError, match="No TranslationManager configured"):
        environment.from_string('{{ t("Yes") }}').render()


def test_full_stack_with_middleware(manager: TranslationManager):
    """
    The middleware locale reaches a template rendered through Starlette.

    The example template reads the request context through the
    ``get_current_locale()`` and ``get_current_tz()`` globals, so nothing about
    the locale has to be threaded through the render context.
    """
    build_manager(manager)
    templates = Jinja2Templates(directory="examples/fastapi_app/templates")
    install_translation_support(templates.env)

    async def index(request: Request) -> HTMLResponse:
        """
        Render the example template.
        """
        return templates.TemplateResponse(
            request,
            "page.html",
            {
                "who": "Ada",
                "item_count": 2,
                "total": 1234.5,
                "today": date(2026, 8, 30),
                "moment": datetime(2026, 8, 30, 14, 30),
            },
        )

    app = Starlette(routes=[Route("/", index)])
    app.add_middleware(TranslationMiddleware, manager=manager, default_locale="en", builtin_locale="en")
    client = TestClient(app)

    french = client.get("/", headers={"Accept-Language": "fr"}).text
    assert "Bonjour, Ada !" in french
    assert '<html lang="fr">' in french
    assert "Hello, Ada!" in client.get("/", headers={"Accept-Language": "en"}).text


def test_full_stack_locale_is_a_locale_object(manager: TranslationManager):
    """
    The rendered page can be read back into a ``Locale`` for further checks.
    """
    build_manager(manager)
    templates = Jinja2Templates(directory="examples/fastapi_app/templates")
    install_translation_support(templates.env)

    async def index(request: Request) -> HTMLResponse:
        """
        Render the page and echo the locale it rendered with.
        """
        rendered = templates.get_template("page.html").render(
            who="Ada",
            item_count=2,
            total=1234.5,
            today=date(2026, 8, 30),
            moment=datetime(2026, 8, 30, 14, 30),
        )
        return HTMLResponse(f"{get_current_locale()}|{rendered}")

    app = Starlette(routes=[Route("/", index)])
    app.add_middleware(TranslationMiddleware, manager=manager, default_locale="en", builtin_locale="en")
    client = TestClient(app)

    text = client.get("/", headers={"Accept-Language": "fr"}).text
    locale, _ = text.split("|", 1)
    assert locale == str(Locale("fr"))
