"""
Tests for the Jinja2 integration.
"""

from datetime import date, datetime

import pytest
from jinja2 import Environment
from jinja2.ext import InternationalizationExtension

from fastapi_simple_i18n.jinja import (
    JinjaConfig,
    build_default_environment,
    get_jinja_config,
    install_translation_support,
)
from fastapi_simple_i18n.locale import get_current_locale, set_current_locale
from fastapi_simple_i18n.models import TranslationEntry


def build_manager(manager) -> None:
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
def env_fixture(manager):
    """
    Return an environment with the helpers installed and a populated manager.
    """
    build_manager(manager)
    return install_translation_support(Environment(autoescape=True))


def test_function_resolves_at_render_time(env, manager):
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


def test_filter_resolves_at_render_time(env):
    """
    The filter form reads the locale at render time too.
    """
    template = env.from_string('{{ "Hello, {name}!" | t(name="Ada") }}')

    set_current_locale("fr")
    assert template.render() == "Bonjour, Ada !"
    set_current_locale("en")
    assert template.render() == "Hello, Ada!"


def test_filter_accepts_variant_keyword_and_positional(env):
    """
    The filter takes the variant as a keyword, as an alias, or positionally.
    """
    set_current_locale("fr")
    assert env.from_string('{{ "Archive" | t(variant="verb") }}').render() == "Archiver"
    assert env.from_string('{{ "Archive" | t(_variant="noun") }}').render() == "Archive"
    assert env.from_string('{{ "Archive" | t("verb") }}').render() == "Archiver"


def test_filter_rejects_more_than_one_positional_argument(env):
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


def test_trans_block_and_context_variant(env):
    """
    {% trans %} blocks are served by the manager, and a context is a variant.
    """
    set_current_locale("fr")
    assert env.from_string("{% trans %}Inbox{% endtrans %}").render() == "Boîte de réception"
    assert env.from_string('{% trans "verb" %}Archive{% endtrans %}').render() == "Archiver"
    assert env.from_string('{% trans "noun" %}Archive{% endtrans %}').render() == "Archive"


def test_trans_block_interpolates_with_percent_syntax(env):
    """
    {% trans %} uses %(name)s interpolation, not {name}.
    """
    set_current_locale("fr")
    rendered = env.from_string("{% trans count=n %}There are {{ n }} messages{% endtrans %}").render(n=3)
    assert rendered == "Il y a 3 messages"


def test_pluralize_is_not_supported(env):
    """
    {% pluralize %} fails with a message that says what to do instead.
    """
    with pytest.raises(NotImplementedError, match="Pluralization is not supported"):
        env.from_string("{% trans count=n %}{{ n }} item{% pluralize %}{{ n }} items{% endtrans %}").render(n=2)


def test_trans_blocks_can_be_disabled(manager):
    """
    With trans_blocks=False the gettext globals are left untouched.
    """
    build_manager(manager)
    environment = Environment(extensions=[InternationalizationExtension])
    environment.install_null_translations()
    null_gettext = environment.globals["gettext"]

    install_translation_support(environment, trans_blocks=False)

    assert environment.globals["gettext"] is null_gettext
    assert "t" in environment.globals


def test_names_are_configurable(manager):
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


def test_reinstalling_updates_the_configuration(manager):
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


def test_formatters_are_registered(manager):
    """
    The number and date helpers are available to templates.
    """
    build_manager(manager)
    environment = build_default_environment()
    set_current_locale("fr")
    assert environment.from_string("{{ t_number(1234.5) }}").render() == "1\u202f234,5"


def test_autoescape_escapes_the_resolved_value(env):
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


def test_full_stack_with_middleware(manager):
    """
    The middleware locale reaches a template rendered through Starlette.
    """
    from starlette.applications import Starlette
    from starlette.responses import HTMLResponse
    from starlette.routing import Route
    from starlette.templating import Jinja2Templates
    from starlette.testclient import TestClient

    from fastapi_simple_i18n.middleware import TranslationMiddleware

    build_manager(manager)
    templates = Jinja2Templates(directory="examples/fastapi_app/templates")
    install_translation_support(templates.env)

    async def index(request):
        """
        Render the example template.
        """
        return HTMLResponse(
            templates.get_template("page.html").render(
                locale=get_current_locale(),
                who="Ada",
                item_count=2,
                total=1234.5,
                today=date(2026, 8, 30),
                moment=datetime(2026, 8, 30, 14, 30),
            ),
        )

    app = Starlette(routes=[Route("/", index)])
    app.add_middleware(TranslationMiddleware, manager=manager, default_locale="en", builtin_locale="en")
    client = TestClient(app)

    assert "Bonjour, Ada !" in client.get("/", headers={"Accept-Language": "fr"}).text
    assert "Hello, Ada!" in client.get("/", headers={"Accept-Language": "en"}).text
