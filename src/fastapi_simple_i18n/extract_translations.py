"""
Extract translatable strings from a module and update its locale files.

This script parses the source directories exposed by a
:class:`~fastapi_simple_i18n.modules.BaseModuleTranslation` subclass and
collects every literal ``t("...")`` call, including its optional ``_variant``.
A call matches on the name alone, so an aliased import or a wrapper is found as
well, given through ``--python-function``.
When the module also declares template directories, they are parsed with
Jinja's own parser (never regex) and the literal ``t()`` calls, ``t()`` filters
and ``{% trans %}`` blocks they contain are collected into the same catalog.
Calls that cannot be extracted (a non-literal key, or a non-literal
``_variant``) are skipped and reported as warnings on ``stderr``. It then
updates each locale JSON file in the module's translation directory:

* New ``(key, variant)`` pairs are added with an empty value and marked as
  ``draft``.
* Existing entries are preserved (their value and draft flag are kept).
* Entries no longer present in the source are removed only with ``--prune``.

Locales are auto-detected from the JSON files already present in the module's
translation directory, plus any extra locale codes passed on the command line.

Usage::

    python -m fastapi_simple_i18n.extract_translations mypackage.i18n:MyModuleTranslation
    python -m fastapi_simple_i18n.extract_translations mypackage.i18n:MyModuleTranslation es fr
    python -m fastapi_simple_i18n.extract_translations mypackage.i18n:MyModuleTranslation --prune
    python -m fastapi_simple_i18n.extract_translations mypackage.i18n:MyModuleTranslation --dry-run

The module reference accepts either ``package.module:ClassName`` or
``package.module.ClassName``.
"""

import argparse
import ast
import importlib
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

from .models import ExtractedKey, Translation, TranslationEntry, dump_translation_file
from .modules import BaseModuleTranslation, has_suffix

# Module holding the Jinja support, imported on demand so a Python-only module
# never needs the optional 'jinja' extra.
JINJA_MODULE = f"{__package__}.jinja"

# Names of the translation function looked for in Python sources. A call matches
# on the name alone, so an alias (``from ... import t as translate``) and an
# attribute (``helpers.t("Key")``) are recognised by the same rule the template
# extractor uses.
DEFAULT_FUNCTION_NAMES = ("t",)


class TranslationCallVisitor(ast.NodeVisitor):
    """
    AST visitor collecting literal ``t()`` calls and their variant.

    Only calls whose first positional argument is a string literal are
    collected. When a ``t()`` call cannot be extracted (a non-literal key, or a
    non-literal ``_variant``) a warning is printed to ``stderr`` with the file,
    the line and a short excerpt of the offending source, so the limitation is
    visible instead of silent.

    Args:
        source: Name of the file being parsed, used in the warnings.
        function_names: Names the translation function may be called by. Matches
            a bare call and an attribute call alike, so wrappers and aliased
            imports are covered.
    """

    def __init__(self, source: str = "<unknown>", function_names: tuple[str, ...] = DEFAULT_FUNCTION_NAMES) -> None:
        """
        Initialize with an empty result set.

        Args:
            source: Name of the file being parsed, used in the warnings.
            function_names: Names the translation function may be called by.
        """
        self.keys: set[ExtractedKey] = set()
        self.source = source
        self.function_names = frozenset(function_names)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802  # pylint: disable=invalid-name
        """
        Visit a call node, collecting ``t("literal", _variant="...")`` usages.
        """
        name = self._called_name(node.func)
        if name in self.function_names and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                self.keys.add((first.value, self._extract_variant(node, first.value)))
            else:
                self._warn(node, f"{name}() called with a non-literal key {self._excerpt(first)}; skipped.")
        self.generic_visit(node)

    @staticmethod
    def _called_name(node: ast.expr) -> str | None:
        """
        Return the name of the function or attribute a call node refers to.
        """
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return None

    def _extract_variant(self, node: ast.Call, key: str) -> str | None:
        """
        Return the literal ``_variant`` keyword value if present.

        A non-literal ``_variant`` is reported as a warning and treated as
        ``None``, which may not match the pair looked up at runtime.
        """
        for keyword in node.keywords:
            if keyword.arg == "_variant":
                if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                    return keyword.value.value
                self._warn(node, f'non-literal _variant {self._excerpt(keyword.value)} for key "{key}"; extracted with no variant.')
        return None

    def _warn(self, node: ast.AST, message: str) -> None:
        """
        Print an extraction warning to ``stderr``, prefixed by location.
        """
        print(f"  Warning: {self.source}:{getattr(node, 'lineno', 0)}: {message}", file=sys.stderr)

    @staticmethod
    def _excerpt(node: ast.AST) -> str:
        """
        Return a short, single-line source excerpt for the given node.
        """
        excerpt = ast.unparse(node).replace("\n", " ")
        return excerpt if len(excerpt) <= 60 else f"{excerpt[:57]}..."


def extract_from_python_file(path: Path, function_names: tuple[str, ...] = DEFAULT_FUNCTION_NAMES) -> set[ExtractedKey]:
    """
    Parse a single Python file and return the collected keys.

    Args:
        path: The file to parse.
        function_names: Names the translation function may be called by.
    """
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, OSError, UnicodeDecodeError) as exc:
        print(f"  Warning: could not parse {path}: {exc}", file=sys.stderr)
        return set()

    visitor = TranslationCallVisitor(source=str(path), function_names=function_names)
    visitor.visit(tree)
    return visitor.keys


def scan_dirs(
    directories: list[Path],
    matches: Callable[[Path], bool],
    extract: Callable[[Path], set[ExtractedKey]],
) -> set[ExtractedKey]:
    """
    Recursively scan directories for the files a predicate accepts.

    Each extractor owns its own predicate, so the file selection rule (suffixes,
    extensions, anything else) lives next to the parsing it belongs to and
    cannot drift between the two.

    Args:
        directories: The directories to walk. A missing directory is reported
            and skipped.
        matches: Predicate deciding whether a file belongs to this extractor.
        extract: Callable applied to each matching file.

    Returns:
        The union of the keys collected from every file.
    """
    all_keys: set[ExtractedKey] = set()
    for directory in directories:
        if not directory.is_dir():
            print(f"  Warning: directory does not exist: {directory}", file=sys.stderr)
            continue
        for path in sorted(directory.rglob("*")):
            if path.is_file() and matches(path):
                all_keys.update(extract(path))
    return all_keys


class PythonExtractor:
    """
    Collect literal ``t()`` calls from Python sources using the ``ast`` module.
    """

    suffixes: tuple[str, ...] = (".py",)
    function_names: tuple[str, ...] = DEFAULT_FUNCTION_NAMES

    def handles(self, path: Path) -> bool:
        """
        Return whether this extractor is responsible for a file.
        """
        return has_suffix(path, self.suffixes)

    def extract(self, path: Path) -> set[ExtractedKey]:
        """
        Parse one Python file and return the collected keys.
        """
        return extract_from_python_file(path, function_names=self.function_names)

    def scan(self, directories: list[Path]) -> set[ExtractedKey]:
        """
        Return the keys collected from the Python files in the directories.
        """
        return scan_dirs(directories, self.handles, self.extract)


class TemplateExtractor:
    """
    Collect literal translation calls from Jinja templates.

    This is a thin adapter: the traversal lives here so all the scanning
    machinery stays in one place, while the parsing and the collection of
    literal calls stay in :mod:`fastapi_simple_i18n.jinja` together with the
    runtime support that defines the names to look for.
    """

    def __init__(self, backend: Any) -> None:
        """
        Wrap the Jinja extractor that does the actual parsing.

        Args:
            backend: A
                :class:`~fastapi_simple_i18n.jinja.JinjaExtractor` instance.
        """
        self.backend = backend

    @property
    def suffixes(self) -> tuple[str, ...]:
        """
        Return the file suffixes treated as templates.
        """
        return self.backend.suffixes

    def handles(self, path: Path) -> bool:
        """
        Return whether this extractor is responsible for a file.
        """
        return self.backend.handles(path)

    def scan(self, directories: list[Path]) -> set[ExtractedKey]:
        """
        Return the keys collected from the templates in the directories.
        """
        return scan_dirs(directories, self.handles, self.backend.extract)


def import_jinja() -> ModuleType:
    """
    Import the Jinja support module.

    The error raised by that module already names the missing extra, so it is
    reused verbatim instead of being wrapped in a second, redundant message.

    Raises:
        SystemExit: If Jinja2 is not installed.
    """
    try:
        return importlib.import_module(JINJA_MODULE)
    except ImportError as exc:  # pragma: no cover - depends on the install extras
        raise SystemExit(str(exc)) from exc


def build_template_extractor(
    module: type[BaseModuleTranslation],
    function_names: list[str] | None = None,
    filter_names: list[str] | None = None,
) -> TemplateExtractor:
    """
    Build the template extractor for a module.

    The environment comes from :meth:`BaseModuleTranslation.get_jinja_environment`
    so extraction sees the same configuration the application renders with; the
    names stored on it by
    :func:`~fastapi_simple_i18n.jinja.install_translation_support` are reused.
    The ``function_names`` and ``filter_names`` arguments override those names,
    for when the environment is not reachable from the module class.

    Args:
        module: The module translation class being extracted.
        function_names: Override for the global function names to look for.
        filter_names: Override for the filter names to look for.

    Returns:
        A :class:`TemplateExtractor` ready to scan.
    """
    jinja = import_jinja()
    environment = module.get_jinja_environment()
    if environment is None:
        environment = jinja.build_default_environment()
    config = jinja.get_jinja_config(environment)
    overrides = jinja.JinjaConfig(
        function_names=tuple(function_names) if function_names else config.function_names,
        filter_names=tuple(filter_names) if filter_names else config.filter_names,
        trans_blocks=config.trans_blocks,
    )
    backend = jinja.JinjaExtractor(environment, overrides)
    backend.suffixes = tuple(module.get_template_suffixes())
    return TemplateExtractor(backend)


def _sort_key(entry: TranslationEntry) -> tuple[str, str]:
    """
    Provide a stable sort order for entries (by key, then variant).
    """
    return (entry.key, entry.variant or "")


def merge_keys_into_translation(
    existing: Translation,
    keys: set[ExtractedKey],
    prune: bool,
) -> tuple[list[TranslationEntry], int, int]:
    """
    Merge extracted keys into an existing translation.

    New pairs are added as empty drafts; existing pairs keep their value and
    flags. With ``prune`` set, pairs missing from the source are dropped.

    Returns:
        A tuple ``(entries, added, removed)`` where ``entries`` is the merged,
        sorted list ready to be written to disk.
    """
    added = 0
    removed = 0
    result: dict[ExtractedKey, TranslationEntry] = {}

    for key, variant in keys:
        found = existing.get(key, variant)
        if found is not None:
            result[(key, variant)] = found
        else:
            result[(key, variant)] = TranslationEntry(key=key, value="", variant=variant, draft=True)
            added += 1

    if not prune:
        for entry in existing.entries():
            pair = (entry.key, entry.variant)
            if pair not in result:
                result[pair] = entry
    else:
        removed = sum(1 for entry in existing.entries() if (entry.key, entry.variant) not in keys)

    ordered = sorted(result.values(), key=_sort_key)
    return ordered, added, removed


def resolve_module(reference: str) -> type[BaseModuleTranslation]:
    """
    Import and return the module translation class from a dotted reference.

    Accepts ``package.module:ClassName`` or ``package.module.ClassName``.

    Raises:
        SystemExit: If the reference cannot be imported or is not a
            :class:`BaseModuleTranslation` subclass.
    """
    if ":" in reference:
        module_path, class_name = reference.split(":", 1)
    else:
        module_path, _, class_name = reference.rpartition(".")
    if not module_path or not class_name:
        raise SystemExit(f"Invalid module reference: {reference!r}")

    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise SystemExit(f"Could not import module {module_path!r}: {exc}") from exc

    try:
        obj = getattr(module, class_name)
    except AttributeError as exc:
        raise SystemExit(f"Module {module_path!r} has no attribute {class_name!r}") from exc

    if not (isinstance(obj, type) and issubclass(obj, BaseModuleTranslation)):
        raise SystemExit(f"{reference!r} is not a BaseModuleTranslation subclass")
    return obj


def run(
    reference: str,
    extra_locales: list[str],
    prune: bool,
    dry_run: bool,
    python_functions: list[str] | None = None,
    jinja_functions: list[str] | None = None,
    jinja_filters: list[str] | None = None,
) -> None:
    """
    Execute the extraction workflow for a module.

    Args:
        reference: Dotted reference to the module translation class.
        extra_locales: Additional locale codes to create/update.
        prune: Whether to remove stale entries.
        dry_run: Whether to only report changes without writing files.
        python_functions: Names the translation function may be called by in
            Python sources. Replaces :data:`DEFAULT_FUNCTION_NAMES`.
        jinja_functions: Global function names to look for in templates.
        jinja_filters: Filter names to look for in templates.
    """
    module = resolve_module(reference)

    source_dirs = module.get_source_dirs()
    template_dirs = module.get_template_dirs()
    translation_dir = module.get_translation_dir()
    function_names = tuple(python_functions) if python_functions else DEFAULT_FUNCTION_NAMES
    print(f"Module: {reference}")
    print(f"Source dirs: {', '.join(str(directory) for directory in source_dirs)}")
    print(f"Python functions: {', '.join(function_names)}")
    if template_dirs:
        print(f"Template dirs: {', '.join(str(directory) for directory in template_dirs)}")
    print(f"Translation dir: {translation_dir}")

    extractor = PythonExtractor()
    extractor.function_names = function_names
    keys = extractor.scan(source_dirs)
    if template_dirs:
        templates = build_template_extractor(module, jinja_functions, jinja_filters)
        print(f"Template suffixes: {', '.join(templates.suffixes)}")
        keys |= templates.scan(template_dirs)

    print(f"Found {len(keys)} unique (key, variant) pairs.")
    if not keys and not module.discover_locales():
        print("Nothing to extract and no existing locales. Done.")
        return

    locales = sorted({*module.discover_locales(), *extra_locales})
    if not locales:
        print("No locales detected and none provided. Pass locale codes, e.g. 'es fr'.")
        return

    print(f"\nUpdating {len(locales)} locale(s): {', '.join(locales)}")
    for locale in locales:
        path = module.get_translation_file(locale)
        existing = Translation.from_file(locale, path) if path.is_file() else Translation(locale)
        entries, added, removed = merge_keys_into_translation(existing, keys, prune=prune)

        status = []
        if added:
            status.append(f"+{added} new (draft)")
        if removed:
            status.append(f"-{removed} removed")
        if not status:
            status.append("no changes")

        if dry_run:
            print(f"  {locale}.json: would apply {', '.join(status)}")
        else:
            dump_translation_file(entries, path)
            print(f"  {locale}.json: {', '.join(status)}")

    print("\nDone.")


def main(argv: list[str] | None = None) -> None:
    """
    Parse command-line arguments and run the extraction.
    """
    parser = argparse.ArgumentParser(
        prog="python -m fastapi_simple_i18n.extract_translations",
        description="Extract translatable strings from a module and update its locale files.",
    )
    parser.add_argument(
        "module",
        help="Module translation class, e.g. 'mypackage.i18n:MyModuleTranslation'.",
    )
    parser.add_argument(
        "locales",
        nargs="*",
        help="Extra locale codes to create/update (in addition to auto-detected ones).",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Remove entries no longer present in the source.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing files.",
    )
    parser.add_argument(
        "--python-function",
        action="append",
        dest="python_functions",
        metavar="NAME",
        help="Name the translation function is called by in Python sources, for an alias or a wrapper. Repeatable. Defaults to 't'.",
    )
    parser.add_argument(
        "--jinja-function",
        action="append",
        dest="jinja_functions",
        metavar="NAME",
        help="Name of the translation function in templates. Repeatable. Overrides the names stored on the environment returned by get_jinja_environment().",
    )
    parser.add_argument(
        "--jinja-filter",
        action="append",
        dest="jinja_filters",
        metavar="NAME",
        help="Name of the translation filter in templates. Repeatable. Overrides the names stored on the environment returned by get_jinja_environment().",
    )
    args = parser.parse_args(argv)
    run(
        args.module,
        args.locales,
        prune=args.prune,
        dry_run=args.dry_run,
        python_functions=args.python_functions,
        jinja_functions=args.jinja_functions,
        jinja_filters=args.jinja_filters,
    )


if __name__ == "__main__":
    main()
