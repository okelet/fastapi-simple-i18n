"""
Tests for the AST-based extraction script.
"""

import sys
from pathlib import Path

import pytest

from fastapi_simple_i18n.extract_translations import (
    TemplateExtractor,
    build_template_extractor,
    extract_from_python_file,
    main,
    merge_keys_into_translation,
    resolve_module,
    run,
)
from fastapi_simple_i18n.jinja import JinjaConfig, JinjaExtractor, build_default_environment, install_translation_support
from fastapi_simple_i18n.models import Translation, TranslationEntry, dump_translation_file
from fastapi_simple_i18n.modules import DEFAULT_TEMPLATE_SUFFIXES


def write_template(path: Path, body: str) -> Path:
    """
    Write a Jinja template file with the given body.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def write_source(path: Path, body: str) -> None:
    """
    Write a Python source file with the given body.
    """
    path.write_text(body, encoding="utf-8")


def test_extract_keys_and_variants(tmp_path: Path):
    """
    The visitor collects literal keys and their _variant argument.
    """
    source = tmp_path / "mod.py"
    write_source(
        source,
        'from fastapi_simple_i18n.helpers import t\n'
        't("Yes")\n'
        't("Archive", _variant="noun")\n'
        't("Hello {name}", name="Ada")\n'
        'x = "not a call"\n'
        't(variable)\n',
    )
    keys = extract_from_python_file(source)
    assert ("Yes", None) in keys
    assert ("Archive", "noun") in keys
    assert ("Hello {name}", None) in keys
    assert len(keys) == 3


def test_non_literal_key_warns_and_is_skipped(tmp_path: Path, capsys):
    """
    A t() call whose key is not a literal is skipped and reported on stderr.
    """
    source = tmp_path / "mod.py"
    write_source(
        source,
        'from fastapi_simple_i18n.helpers import t\n'
        'name = "Yes"\n'
        't(name)\n'
        't(f"Hello {name}")\n',
    )
    keys = extract_from_python_file(source)
    assert keys == set()

    captured = capsys.readouterr()
    assert "mod.py:3" in captured.err
    assert 'non-literal key name' in captured.err
    assert "mod.py:4" in captured.err
    assert "non-literal key f'Hello {name}'" in captured.err


def test_aliased_and_wrapped_names_are_extracted(tmp_path: Path):
    """
    A call matches on the name alone, so aliases and wrappers are collected.
    """
    source = tmp_path / "mod.py"
    write_source(
        source,
        'from fastapi_simple_i18n.helpers import t as translate\n'
        'translate("Aliased import")\n'
        'translate("Archive", _variant="verb")\n'
        'i18n.translate("Attribute access")\n'
        'def tr(key, **kwargs):\n'
        '    return translate(key, **kwargs)\n'
        'tr("Through a wrapper")\n'
        't("Plain t")\n',
    )

    # By default only the literal name t counts; the alias is just another name.
    assert extract_from_python_file(source) == {("Plain t", None)}

    # The given names replace t rather than extend it, and the attribute call
    # matches on the name after the dot, like the template extractor.
    renamed = extract_from_python_file(source, function_names=("translate", "tr"))

    assert renamed == {
        ("Aliased import", None),
        ("Archive", "verb"),
        ("Attribute access", None),
        ("Through a wrapper", None),
    }


def test_warning_names_the_function_that_was_called(tmp_path: Path, capsys):
    """
    A non-literal key is reported with the name the call actually used.
    """
    source = tmp_path / "mod.py"
    write_source(source, 'from fastapi_simple_i18n.helpers import t as translate\ntranslate(dynamic)\n')

    extract_from_python_file(source, function_names=("translate",))

    assert "translate() called with a non-literal key dynamic" in capsys.readouterr().err


def test_non_literal_variant_warns_and_is_dropped(tmp_path: Path, capsys):
    """
    A non-literal _variant is reported and the pair is extracted with no variant.
    """
    source = tmp_path / "mod.py"
    write_source(
        source,
        'from fastapi_simple_i18n.helpers import t\n'
        'kind = "noun"\n'
        't("Archive", _variant=kind)\n'
        't("Other", _variant=1)\n',
    )
    keys = extract_from_python_file(source)
    assert keys == {("Archive", None), ("Other", None)}

    captured = capsys.readouterr()
    assert 'non-literal _variant kind for key "Archive"; extracted with no variant.' in captured.err
    assert 'non-literal _variant 1 for key "Other"; extracted with no variant.' in captured.err


def test_merge_adds_new_as_draft():
    """
    New (key, variant) pairs are added with an empty value and draft=True.
    """
    existing = Translation("es", [TranslationEntry(key="Yes", value="Sí")])
    keys = {("Yes", None), ("No", None)}
    entries, added, removed = merge_keys_into_translation(existing, keys, prune=False)
    by_key = {(e.key, e.variant): e for e in entries}
    assert added == 1
    assert removed == 0
    assert by_key[("Yes", None)].value == "Sí"
    assert by_key[("No", None)].value == ""
    assert by_key[("No", None)].draft is True


def test_merge_preserves_existing_when_not_pruning():
    """
    Without prune, entries missing from source are preserved.
    """
    existing = Translation("es", [TranslationEntry(key="Old", value="Viejo")])
    entries, added, removed = merge_keys_into_translation(existing, {("New", None)}, prune=False)
    keys = {(e.key, e.variant) for e in entries}
    assert ("Old", None) in keys
    assert ("New", None) in keys
    assert added == 1
    assert removed == 0


def test_merge_prunes_stale():
    """
    With prune, entries missing from source are removed.
    """
    existing = Translation("es", [TranslationEntry(key="Old", value="Viejo")])
    entries, _added, removed = merge_keys_into_translation(existing, {("New", None)}, prune=True)
    keys = {(e.key, e.variant) for e in entries}
    assert ("Old", None) not in keys
    assert removed == 1


def build_package(tmp_path: Path) -> str:
    """
    Create an importable package with a module translation class and sources.

    Returns the dotted reference to the translation class.
    """
    pkg = tmp_path / "extract_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "views.py").write_text(
        'from fastapi_simple_i18n.helpers import t\n'
        'a = t("Yes")\n'
        'b = t("Archive", _variant="noun")\n',
        encoding="utf-8",
    )
    write_template(
        pkg / "templates" / "page.html",
        '<h1>{{ t("Welcome") }}</h1>\n{{ "Archive" | t(variant="verb") }}\n{% trans %}Inbox{% endtrans %}\n',
    )
    (pkg / "i18n.py").write_text(
        "from pathlib import Path\n"
        "from fastapi_simple_i18n.modules import BaseModuleTranslation\n"
        "\n"
        "class Mod(BaseModuleTranslation):\n"
        "    @classmethod\n"
        "    def get_source_dirs(cls):\n"
        "        return [Path(__file__).parent]\n"
        "    @classmethod\n"
        "    def get_template_dirs(cls):\n"
        "        return [Path(__file__).parent / 'templates']\n"
        "    @classmethod\n"
        "    def get_translation_dir(cls):\n"
        "        return Path(__file__).parent / 'translations'\n",
        encoding="utf-8",
    )
    return "extract_pkg.i18n:Mod"


def test_resolve_module_and_run(tmp_path: Path, monkeypatch):
    """
    run() extracts keys and writes locale files, marking new keys as draft.
    """
    reference = build_package(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))

    module = resolve_module(reference)
    # Pre-seed es.json with one existing translation to verify preservation.
    dump_translation_file(
        [TranslationEntry(key="Yes", value="Sí")],
        module.get_translation_file("es"),
    )

    run(reference, extra_locales=["fr"], prune=False, dry_run=False)

    es = Translation.from_file("es", module.get_translation_file("es"))
    fr = Translation.from_file("fr", module.get_translation_file("fr"))

    # Existing translation preserved.
    assert es.get("Yes").value == "Sí"
    assert es.get("Yes").draft is False
    # New variant key added as draft.
    assert es.get("Archive", "noun").value == ""
    assert es.get("Archive", "noun").draft is True
    # Extra locale created with drafts.
    assert fr.get("Yes").draft is True
    assert fr.get("Archive", "noun").draft is True
    # Template strings land in the same catalog.
    assert es.get("Welcome").draft is True
    assert es.get("Inbox").draft is True
    assert es.get("Archive", "verb").draft is True

    # Clean up imported modules so other tests are unaffected.
    for name in list(sys.modules):
        if name.startswith("extract_pkg"):
            del sys.modules[name]


def test_run_writes_the_file_under_the_spelling_it_was_given(tmp_path: Path, monkeypatch):
    """
    A locale may be given in any spelling, and the file keeps that name.

    The name on disk is what a translator sees in the UI and in git, so it is
    preserved; the locale itself is resolved, so a later lookup finds it through
    any other spelling.
    """
    reference = build_package(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    module = resolve_module(reference)

    run(reference, extra_locales=["ES-es"], prune=False, dry_run=False)

    path = module.get_translation_file("ES-es")
    assert path.name == "ES-es.json"
    assert Translation.from_file("es-es", path).get("Yes").draft is True
    assert module.discover_locales() == ["ES-es"]

    for name in list(sys.modules):
        if name.startswith("extract_pkg"):
            del sys.modules[name]


def test_run_rejects_an_unusable_locale(tmp_path: Path, monkeypatch):
    """
    A locale that is not one is reported before anything is written.

    The script is a batch tool, so a bad locale on the command line ends the
    run with a clear message instead of creating a file nobody can serve.
    """
    reference = build_package(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    module = resolve_module(reference)

    with pytest.raises(SystemExit, match="Invalid locale 'nope'"):
        run(reference, extra_locales=["es", "nope"], prune=False, dry_run=False)

    assert not module.get_translation_file("es").exists()

    for name in list(sys.modules):
        if name.startswith("extract_pkg"):
            del sys.modules[name]


def test_run_rejects_a_locale_file_named_after_something_else(tmp_path: Path, monkeypatch):
    """
    A file in the translation directory must be named after a locale.

    A ``notes.json`` next to the locale files is a mistake (a backup, a
    half-written file), and registering it would produce a locale the library
    cannot resolve.
    """
    reference = build_package(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    module = resolve_module(reference)
    module.get_translation_dir().mkdir(parents=True, exist_ok=True)
    (module.get_translation_dir() / "notes.json").write_text('{"translations": []}', encoding="utf-8")

    with pytest.raises(SystemExit, match="Invalid locale 'notes'"):
        run(reference, extra_locales=[], prune=False, dry_run=False)

    for name in list(sys.modules):
        if name.startswith("extract_pkg"):
            del sys.modules[name]


def test_template_extraction_covers_every_form(tmp_path: Path):
    """
    The function, the filter and trans blocks all feed the same catalog.
    """
    template = write_template(
        tmp_path / "page.html",
        '<h1>{{ t("Hello, {name}!", name=who) }}</h1>\n'
        '{{ t("Archive", _variant="verb") }}\n'
        '{{ "Inbox" | t }}\n'
        "{{ title | t }}\n"
        "{% trans %}Welcome{% endtrans %}\n"
        '{% trans "noun" %}Archive{% endtrans %}\n'
        '{{ _("Signed in") }}\n',
    )

    keys = JinjaExtractor().extract(template)

    assert keys == {
        ("Hello, {name}!", None),
        ("Archive", "verb"),
        ("Inbox", None),
        ("Welcome", None),
        ("Archive", "noun"),
        ("Signed in", None),
    }


def test_template_non_literal_key_warns_and_is_skipped(tmp_path: Path, capsys):
    """
    A call whose key is not a literal is reported with file and line.
    """
    template = write_template(
        tmp_path / "page.html",
        '<h1>{{ t("Yes") }}</h1>\n{{ t(dynamic_key) }}\n{{ dynamic | t }}\n',
    )

    keys = JinjaExtractor().extract(template)

    assert keys == {("Yes", None)}
    captured = capsys.readouterr()
    assert "page.html:2" in captured.err
    assert "non-literal key" in captured.err
    assert "page.html:3" in captured.err


def test_template_pluralize_warns_and_is_skipped(tmp_path: Path, capsys):
    """
    Pluralization is reported rather than silently half-extracted.
    """
    template = write_template(
        tmp_path / "page.html",
        "{% trans count=n %}{{ n }} item{% pluralize %}{{ n }} items{% endtrans %}\n",
    )

    assert JinjaExtractor().extract(template) == set()
    assert "pluralization is not supported" in capsys.readouterr().err


def test_template_syntax_error_warns_and_yields_nothing(tmp_path: Path, capsys):
    """
    A broken template is reported and never blocks the extraction.
    """
    template = write_template(tmp_path / "page.html", "{% for %}\n")

    assert JinjaExtractor().extract(template) == set()
    assert "could not parse template" in capsys.readouterr().err


def test_template_raw_blocks_are_ignored(tmp_path: Path):
    """
    Text inside {% raw %} is not parsed, so it is not extracted.
    """
    template = write_template(
        tmp_path / "page.html",
        '{% raw %}{{ t("Not real") }}{% endraw %}{{ t("Real") }}\n',
    )

    assert JinjaExtractor().extract(template) == {("Real", None)}


def test_template_scanner_only_reads_declared_suffixes(tmp_path: Path):
    """
    A file that is not a template suffix is never parsed.
    """
    write_template(tmp_path / "notes.txt", '{{ t("Never scanned") }}\n')
    write_template(tmp_path / "page.html", '{{ t("Scanned") }}\n')
    extractor = TemplateExtractor(JinjaExtractor())

    assert extractor.suffixes == DEFAULT_TEMPLATE_SUFFIXES
    assert extractor.scan([tmp_path]) == {("Scanned", None)}


def test_template_scanner_reads_compound_suffixes(tmp_path: Path):
    """
    Templates named page.html.j2 or page.j2.html are scanned too.
    """
    write_template(tmp_path / "page.html.j2", '{{ t("Html then j2") }}\n')
    write_template(tmp_path / "page.j2.html", '{{ t("J2 then html") }}\n')
    write_template(tmp_path / "page.j2", '{{ t("Bare j2") }}\n')
    extractor = TemplateExtractor(JinjaExtractor())

    assert extractor.scan([tmp_path]) == {("Html then j2", None), ("J2 then html", None)}


def test_template_extractor_uses_the_module_suffixes(tmp_path: Path, monkeypatch):
    """
    A module can declare which suffixes are templates.
    """
    reference = build_package(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    module = resolve_module(reference)
    templates = tmp_path / "extract_pkg" / "templates"
    write_template(templates / "page.tpl", '{{ t("From a .tpl file") }}\n')

    assert build_template_extractor(module).suffixes == DEFAULT_TEMPLATE_SUFFIXES

    module.get_template_suffixes = classmethod(lambda cls: (".tpl",))  # type: ignore[method-assign]
    extractor = build_template_extractor(module)

    assert extractor.suffixes == (".tpl",)
    assert extractor.scan([templates]) == {("From a .tpl file", None)}

    for name in list(sys.modules):
        if name.startswith("extract_pkg"):
            del sys.modules[name]


def test_template_names_can_be_overridden_from_the_command_line(tmp_path: Path, monkeypatch):
    """
    The CLI names win over the ones stored on the module's environment.
    """
    reference = build_package(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    module = resolve_module(reference)
    templates = tmp_path / "extract_pkg" / "templates"
    write_template(templates / "renamed.html", '{{ translate("Via translate") }}\n')

    assert ("Via translate", None) not in build_template_extractor(module).scan([templates])

    overridden = build_template_extractor(module, function_names=["translate"])

    assert ("Via translate", None) in overridden.scan([templates])

    for name in list(sys.modules):
        if name.startswith("extract_pkg"):
            del sys.modules[name]


def test_wrapper_and_aliased_names_are_extracted(tmp_path: Path):
    """
    Wrapper helpers and attribute access to a translation helper are found.
    """
    templates = tmp_path / "templates"
    write_template(templates / "page.html", '{{ tr("Wrapper") }}\n{{ i18n.t("Aliased") }}\n')
    environment = install_translation_support(
        build_default_environment(),
        function_name=("t", "tr"),
        filter_name=("t", "tx"),
    )
    write_template(templates / "filters.html", '{{ "One" | tx }}\n{{ "Two" | t }}\n')

    keys = TemplateExtractor(JinjaExtractor(environment)).scan([templates])

    assert keys == {("Wrapper", None), ("Aliased", None), ("One", None), ("Two", None)}


def test_several_names_can_be_given_for_functions_and_filters(tmp_path: Path):
    """
    Several wrapper names are looked for, and the given ones replace the stored ones.
    """
    templates = tmp_path / "templates"
    for name in ("one.html", "two.html", "three.html"):
        write_template(
            templates / name,
            '{{ one("Fn one") }}{{ two("Fn two") }}{{ "Filter one" | a }}{{ "Filter two" | b }}\n',
        )
    backend = JinjaExtractor(
        build_default_environment(),
        JinjaConfig(function_names=("one", "two"), filter_names=("a", "b")),
    )

    assert TemplateExtractor(backend).scan([templates]) == {
        ("Fn one", None),
        ("Fn two", None),
        ("Filter one", None),
        ("Filter two", None),
    }


def test_the_python_function_option_can_be_repeated(tmp_path: Path, monkeypatch, capsys):
    """
    Repeating --python-function makes every alias and wrapper count.
    """
    reference = build_package(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / "extract_pkg" / "views.py").write_text(
        'from fastapi_simple_i18n.helpers import t as translate\n'
        "import fastapi_simple_i18n.helpers as h\n"
        'translate("One")\n'
        'tr("Two")\n'
        'h.tr("Three")\n'
        'h.t("Four")\n',
        encoding="utf-8",
    )
    # page.html contributes the {% trans %} key, which no option can rename.
    (tmp_path / "extract_pkg" / "templates" / "page.html").write_text(
        "{% trans %}Trans{% endtrans %}{{ t('Ignored') }}\n",
        encoding="utf-8",
    )

    main([reference, "es", "--dry-run"])

    # The trans block, the t() call in the template and h.t("Four"); the aliases
    # are just other names, so they are not picked up.
    default = capsys.readouterr().out
    assert "Python functions: t" in default
    assert "Found 3 unique (key, variant) pairs." in default

    main(
        [
            reference,
            "es",
            "--dry-run",
            "--python-function",
            "translate",
            "--python-function",
            "tr",
        ],
    )

    # The two template keys, which no Python option touches, plus the three
    # alias calls. h.t("Four") is gone: the option replaces the names, it does
    # not extend them.
    renamed = capsys.readouterr().out
    assert "Python functions: translate, tr" in renamed
    assert "Found 5 unique (key, variant) pairs." in renamed

    for name in list(sys.modules):
        if name.startswith("extract_pkg"):
            del sys.modules[name]


def test_the_jinja_name_options_can_be_repeated(tmp_path: Path, monkeypatch, capsys):
    """
    Repeating --jinja-function and --jinja-filter makes every name count.
    """
    reference = build_package(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    templates = tmp_path / "extract_pkg" / "templates"
    write_template(
        templates / "wrappers.html",
        '{{ one("Fn one") }}{{ two("Fn two") }}{{ "Filter one" | a }}{{ "Filter two" | b }}\n',
    )

    main(
        [
            reference,
            "es",
            "--dry-run",
            "--jinja-function",
            "one",
            "--jinja-function",
            "two",
            "--jinja-filter",
            "a",
            "--jinja-filter",
            "b",
        ],
    )

    # Two from views.py, one {% trans %} block (name-independent), and four
    # reachable only through the given names. The "Welcome" and "Archive" keys
    # of page.html are gone: the options replace the names, they do not add to them.
    assert "Found 7 unique (key, variant) pairs." in capsys.readouterr().out

    for name in list(sys.modules):
        if name.startswith("extract_pkg"):
            del sys.modules[name]


def test_jinja_config_is_read_from_the_module_environment(tmp_path: Path, monkeypatch):
    """
    A module returning its own environment gets its names and suffixes used.
    """
    reference = build_package(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    module = resolve_module(reference)
    templates = tmp_path / "extract_pkg" / "templates"
    write_template(templates / "renamed.html", '{{ translate("Via translate") }}\n')

    environment = install_translation_support(build_default_environment(), function_name="translate")
    module.get_jinja_environment = classmethod(lambda cls: environment)  # type: ignore[method-assign]

    assert ("Via translate", None) in build_template_extractor(module).scan([templates])

    for name in list(sys.modules):
        if name.startswith("extract_pkg"):
            del sys.modules[name]
