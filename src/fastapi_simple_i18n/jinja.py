"""
Jinja2 support for fastapi-simple-i18n.

Installs the translation helpers into a Jinja environment so templates
translate strings the same way Python code does: the same ``t()`` function,
the same ``(key, variant)`` pair, the same ``{name}`` placeholders, and the same
lazy resolution against the locale that is active at render time.

Three things become available in templates:

* ``t("Key", ...)`` as a global function, and ``"Key" | t(...)`` as a filter.
  Both names are configurable, so templates may use ``translate()`` or anything
  else instead of ``t``.
* ``{% trans %}...{% endtrans %}`` blocks, served by this library's manager
  instead of gettext catalogs. An optional context (``{% trans "verb" %}...``)
  maps to the library's variant. Pluralization is not supported.
* ``t_number``, ``t_date``, ``t_time`` and ``t_datetime`` for locale-aware
  formatting.

This is the only module that depends on Jinja2, which ships as the optional
``jinja`` extra (``pip install fastapi-simple-i18n[jinja]``).
"""

import sys
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

try:
    from jinja2 import Environment, nodes, pass_context
    from jinja2.exceptions import TemplateSyntaxError
    from jinja2.ext import GETTEXT_FUNCTIONS, InternationalizationExtension
    from jinja2.runtime import Context
except ImportError as exc:  # pragma: no cover - depends on the install extras
    raise ImportError("Jinja2 support requires Jinja. Install the optional extra with 'pip install fastapi-simple-i18n[jinja]' (or add 'jinja2' to your project).") from exc

from .helpers import (
    TranslatableStr,
    lazy_t,
    lazy_t_date,
    lazy_t_datetime,
    lazy_t_number,
    lazy_t_time,
    t,
    t_date,
    t_datetime,
    t_number,
    t_time,
)
from .locale import get_current_locale
from .models import ExtractedKey
from .modules import DEFAULT_TEMPLATE_SUFFIXES, has_suffix
from .registry import get_translation_manager

# Attribute under which the configuration is stored on an environment. The
# extraction script reads it from the same environment the application renders
# with, so it always looks for the names that are actually in use.
CONFIG_ATTRIBUTE = "fastapi_simple_i18n"

# Default names of the translation function (global) and filter.
DEFAULT_FUNCTION_NAME = "t"
DEFAULT_FILTER_NAME = "t"

# Keyword arguments accepted to select a variant. The library's own ``t()``
# takes ``_variant``; templates read better with ``variant``, so both are
# accepted and ``_variant`` wins. That keeps a translation with a ``{variant}``
# placeholder usable, at the cost of spelling the keyword with an underscore.
VARIANT_KEYWORDS = ("_variant", "variant")

# The formatting helpers are always registered under their canonical names.
FORMATTERS: dict[str, Callable[..., str]] = {
    "t_number": t_number,
    "t_date": t_date,
    "t_time": t_time,
    "t_datetime": t_datetime,
}

# The lazy formatters are always registered under their canonical names too.
LAZY_FORMATTERS: dict[str, Callable[..., object]] = {
    "lazy_t_number": lazy_t_number,
    "lazy_t_date": lazy_t_date,
    "lazy_t_time": lazy_t_time,
    "lazy_t_datetime": lazy_t_datetime,
}


@dataclass(frozen=True, slots=True)
class JinjaConfig:
    """
    The names under which the translation helpers are installed.

    Attributes:
        function_names: Names of the global eager translation function.
            ``t("Key")``. Returns a real ``str`` resolved at call time.
        filter_names: Names of the eager translation filter. ``"Key" | t``.
        lazy_function_names: Names of the global lazy translation function.
            ``lazy_t("Key")``. Returns a :class:`LazyTranslatableStr` that
            resolves at render time via Jinja's default ``finalize`` (which
            calls ``str()`` on the output value, so no ``| string`` wrapper
            is needed inside ``{{ }}``).
        lazy_filter_names: Names of the lazy translation filter. ``"Key" | lazy_t``.
        trans_blocks: Whether ``{% trans %}`` blocks are served by this library.
    """

    function_names: tuple[str, ...] = (DEFAULT_FUNCTION_NAME,)
    filter_names: tuple[str, ...] = (DEFAULT_FILTER_NAME,)
    lazy_function_names: tuple[str, ...] = ("lazy_" + DEFAULT_FUNCTION_NAME,)
    lazy_filter_names: tuple[str, ...] = ("lazy_" + DEFAULT_FILTER_NAME,)
    trans_blocks: bool = True


def get_jinja_config(environment: Environment) -> JinjaConfig:
    """
    Return the configuration stored on an environment.

    Set by :func:`install_translation_support`. Returns the default
    configuration when the environment was never installed into, so callers can
    always rely on the names being available.
    """
    config = getattr(environment, CONFIG_ATTRIBUTE, None)
    return config if isinstance(config, JinjaConfig) else JinjaConfig()


def _as_names(value: str | Sequence[str] | None, default: tuple[str, ...]) -> tuple[str, ...]:
    """
    Normalize a name or a sequence of names into a non-empty tuple of names.

    Args:
        value: A single name, a sequence of names, or ``None`` for the default.
        default: The names to use when ``value`` is ``None``.

    Raises:
        ValueError: If an empty sequence is given.
    """
    if value is None:
        return default
    names = (value,) if isinstance(value, str) else tuple(value)
    if not names:
        raise ValueError("At least one name is required")
    return names


def _with_variant_alias(params: dict[str, object]) -> dict[str, object]:
    """
    Accept ``variant=`` as a template-friendly alias for ``_variant=``.

    Args:
        params: The keyword arguments of a template translation call. Mutated in
            place and returned for convenience.
    """
    if "_variant" not in params and "variant" in params:
        params["_variant"] = params.pop("variant")
    return params


# The single callable installed as both the global function and the filter:
# with ``@pass_context`` the signature is ``(context, value, *args, **params)``
# for either role.
#
# ``@pass_context`` is not optional. Jinja's optimizer evaluates a *filter* call
# whose arguments are all constants while the template is being compiled, and a
# translation call with a literal key is exactly that: without this decorator
# ``{{ "Archive" | t }}`` would be translated once, with whatever locale was
# active at compile time, and every later request would reuse that string. A
# context-taking callable is never folded, so the locale is read at render time
# and cached templates stay correct. The global ``t()`` happens to survive
# folding, but both roles share this callable so they cannot drift apart.
@pass_context
def template_translate(context: Context, value: str, *args: object, **params: object) -> TranslatableStr:
    """
    Return an eager translation for a key given as the value or the first argument.

    The first positional argument selects the variant and the keyword arguments
    are format parameters, exactly as in :func:`~fastapi_simple_i18n.helpers.t`.
    """
    if len(args) > 1:
        raise TypeError("A template translation takes at most one positional argument (the variant)")
    return t(value, *args, **_with_variant_alias(params))


# Same shape as :func:`template_translate`, but returns a lazy wrapper. Jinja's
# default ``finalize`` (which calls ``str()`` on every output value) resolves
# the lazy object at render time, so ``{{ lazy_t("Key") }}`` and
# ``{{ "Key" | lazy_t }}`` work in templates without any wrapper. The same
# ``@pass_context`` rationale as ``template_translate`` applies: a filter call
# with literal arguments would otherwise be constant-folded at compile time.
@pass_context
def template_lazy_translate(context: Context, value: str, *args: object, **params: object) -> object:
    """
    Return a lazy translation for a key given as the value or the first argument.

    The first positional argument selects the variant and the keyword arguments
    are format parameters, exactly as in :func:`~fastapi_simple_i18n.helpers.lazy_t`.

    The returned :class:`~fastapi_simple_i18n.helpers.LazyTranslatableStr` is
    NOT a ``str`` subclass — but Jinja's default render pipeline calls ``str()``
    on every output value (``env.finalize`` defaults to :func:`str`), so
    ``{{ lazy_t("Key") }}`` renders correctly without any wrapper. Only
    boundaries that bypass Jinja's output stage (``json.dumps`` inside
    ``| tojson``, Pydantic ``str`` fields, ``urllib.parse.quote``) still
    need an explicit ``str()`` at the call site.
    """
    if len(args) > 1:
        raise TypeError("A template translation takes at most one positional argument (the variant)")
    return lazy_t(value, *args, **_with_variant_alias(params))


def _resolve(message: str, variant: str | None = None) -> str:
    """
    Resolve a message with the active manager and locale.

    Used by the ``{% trans %}`` callables, which must return the raw translated
    string: Jinja applies the interpolation and the escaping itself.
    """
    return get_translation_manager().translate(message, variant=variant, locale=get_current_locale())


def _make_gettext_callables() -> tuple[Callable[..., str], Callable[..., str], Callable[..., str]]:
    """
    Build the ``gettext``-style callables that back ``{% trans %}`` blocks.

    Returns:
        A ``(gettext, ngettext, pgettext)`` tuple. ``ngettext`` always raises
        because pluralization is not supported.
    """

    def gettext(message: str) -> str:
        """
        Return the translation of a message, uninterpolated.
        """
        return _resolve(message)

    def pgettext(context: str, message: str) -> str:
        """
        Return the translation of a message for a context, mapped to a variant.
        """
        return _resolve(message, variant=context)

    def ngettext(singular: str, plural: str, n: int) -> str:
        """
        Fail with an actionable message: pluralization is not supported.
        """
        raise NotImplementedError("Pluralization is not supported. Use one key per form with the variant argument instead, for example t('There are {n} items', _variant='plural').")

    return gettext, ngettext, pgettext


def install_translation_support(
    environment: Environment,
    *,
    function_name: str | Sequence[str] | None = None,
    filter_name: str | Sequence[str] | None = None,
    lazy_function_name: str | Sequence[str] | None = None,
    lazy_filter_name: str | Sequence[str] | None = None,
    trans_blocks: bool = True,
) -> Environment:
    """
    Add the translation helpers to a Jinja environment.

    This is a plain function rather than a Jinja ``Extension`` because
    extensions cannot take configuration arguments and these names are meant to
    be configurable. It is safe to call more than once, and it returns the
    environment so it can be chained.

    The installer registers two flavours of the translation function and
    formatter, plus the ``trans`` block:

    * Eager (``t`` / ``t_number`` / ``t_date`` / ``t_time`` / ``t_datetime``):
      resolve at call time against the active locale and return a real ``str``.
      Works inside ``{{ }}`` without any wrapper.
    * Lazy (``lazy_t`` / ``lazy_t_number`` / ``lazy_t_date`` / ``lazy_t_time``
      / ``lazy_t_datetime``): return a string-like wrapper that resolves at
      render time. Jinja's default ``finalize`` already calls ``str()`` on
      every output value, so ``{{ lazy_t("Key") }}`` and
      ``{{ lazy_t_number(1234.5) }}`` work inside ``{{ }}`` without any
      wrapper. The same output, fed to ``| tojson`` or any other boundary
      that goes through the C-level ``str`` protocol (``json.dumps``,
      ``urllib.parse.quote``, Pydantic str fields), still needs an explicit
      ``str()`` — use ``{{ lazy_t("Key") | string | tojson }}`` there.

    Args:
        environment: The environment to install into. Usually
            ``Jinja2Templates(...).env`` with FastAPI or Starlette.
        function_name: Name, or names, for the global eager translation
            function. Defaults to ``"t"``.
        filter_name: Name, or names, for the eager translation filter.
            Defaults to ``"t"``.
        lazy_function_name: Name, or names, for the global lazy translation
            function. Defaults to ``"lazy_t"``.
        lazy_filter_name: Name, or names, for the lazy translation filter.
            Defaults to ``"lazy_t"``.
        trans_blocks: Whether to serve ``{% trans %}`` blocks from this
            library. Enabling it loads ``jinja2.ext.i18n`` and replaces its
            ``gettext``, ``ngettext`` and ``pgettext`` globals; pass ``False``
            to leave an existing gettext setup untouched.

    Returns:
        The same environment, with the helpers installed and the configuration
        stored on it (see :func:`get_jinja_config`).
    """
    defaults = JinjaConfig()
    config = JinjaConfig(
        function_names=_as_names(function_name, defaults.function_names),
        filter_names=_as_names(filter_name, defaults.filter_names),
        lazy_function_names=_as_names(lazy_function_name, defaults.lazy_function_names),
        lazy_filter_names=_as_names(lazy_filter_name, defaults.lazy_filter_names),
        trans_blocks=trans_blocks,
    )

    for name in config.function_names:
        environment.globals[name] = template_translate
    for name, formatter in FORMATTERS.items():
        environment.globals.setdefault(name, formatter)
    for name in config.filter_names:
        environment.filters[name] = template_translate

    for name in config.lazy_function_names:
        environment.globals[name] = template_lazy_translate
    for name, formatter in LAZY_FORMATTERS.items():
        environment.globals.setdefault(name, formatter)
    for name in config.lazy_filter_names:
        environment.filters[name] = template_lazy_translate

    if config.trans_blocks:
        environment.add_extension(InternationalizationExtension)
        gettext, ngettext, pgettext = _make_gettext_callables()
        environment.install_gettext_callables(gettext=gettext, ngettext=ngettext, newstyle=False, pgettext=pgettext)

    # ``Environment.extend()`` is the usual way to store extension configuration,
    # but it deliberately ignores attributes that already exist, so it would keep
    # the configuration of a previous call. Assigning directly is what makes a
    # second installation with different names actually take effect.
    setattr(environment, CONFIG_ATTRIBUTE, config)
    return environment


def build_default_environment() -> Environment:
    """
    Build an environment with the translation helpers already installed.

    Used as the extraction fallback for modules that do not declare their own
    environment. It has no loader; supply one to render templates.
    """
    return install_translation_support(Environment(autoescape=True))


def _called_name(node: nodes.Node) -> str | None:
    """
    Return the name of the function or attribute a call node refers to.
    """
    if isinstance(node, nodes.Name):
        return node.name
    if isinstance(node, nodes.Getattr):
        return node.attr
    return None


def _literal_string(node: nodes.Node | None) -> str | None:
    """
    Return the value of a node if it is a string constant, else ``None``.
    """
    if isinstance(node, nodes.Const) and isinstance(node.value, str):
        return node.value
    return None


def _warn(source: str, lineno: int, message: str) -> None:
    """
    Print an extraction warning to ``stderr``, prefixed by location.
    """
    print(f"  Warning: {source}:{lineno}: {message}", file=sys.stderr)


def _iter_lines(source: str) -> Iterator[str]:
    """
    Yield the source lines, so an excerpt can be shown for a node's line.
    """
    yield from source.splitlines()


class TemplateCallVisitor:
    """
    Collect literal translation calls from a parsed Jinja template.

    Recognizes the configured global function names, the configured filter
    names, and the ``gettext``-style calls that ``{% trans %}`` blocks compile
    to. A call whose key is not a string literal is reported as a warning and
    skipped, mirroring the behaviour of the Python extractor.
    """

    def __init__(self, config: JinjaConfig, source_name: str, source: str) -> None:
        """
        Initialize with an empty result set.

        Args:
            config: The names to look for.
            source_name: Name of the template, used in warnings.
            source: The raw template text, used to build excerpts.
        """
        self.config = config
        self.source_name = source_name
        self.keys: set[ExtractedKey] = set()
        self._lines = list(_iter_lines(source))

    def visit(self, template: nodes.Template) -> set[ExtractedKey]:
        """
        Walk a parsed template and return the collected pairs.
        """
        for node in template.find_all(nodes.Call):
            self._visit_call(node)
        for node in template.find_all(nodes.Filter):
            self._visit_filter(node)
        return self.keys

    def _visit_call(self, node: nodes.Call) -> None:
        """
        Handle a call node, either a translation function or a gettext call.
        """
        name = _called_name(node.node)
        if name is None:
            return
        if name in self.config.function_names:
            self._collect(node, node.args[0] if node.args else None, node.kwargs)
        elif self.config.trans_blocks and name in GETTEXT_FUNCTIONS:
            self._visit_gettext_call(node, name)

    def _visit_filter(self, node: nodes.Filter) -> None:
        """
        Handle a filter node whose name is a translation filter.

        For a filter the key is the piped value, not the first argument.
        """
        if node.name in self.config.filter_names:
            self._collect(node, node.node, node.kwargs)

    def _visit_gettext_call(self, node: nodes.Call, name: str) -> None:
        """
        Handle a ``{% trans %}`` block or an explicit gettext call.
        """
        if name in ("ngettext", "npgettext"):
            _warn(
                self.source_name,
                node.lineno,
                "pluralization is not supported; use one key per form with the variant argument instead. Skipped.",
            )
            return
        # ``pgettext(context, message)`` takes the context first, and a context
        # is exactly this library's variant.
        with_context = name == "pgettext"
        offset = 1 if with_context else 0
        if len(node.args) <= offset:
            _warn(self.source_name, node.lineno, f"{name}() called with no message; skipped.")
            return
        self._collect(node, node.args[offset], node.kwargs, variant_node=node.args[0] if with_context else None)

    def _collect(
        self,
        node: nodes.Node,
        key_node: nodes.Node | None,
        kwargs: list[nodes.Keyword],
        variant_node: nodes.Node | None = None,
    ) -> None:
        """
        Record one ``(key, variant)`` pair, warning about non-literal parts.
        """
        key = _literal_string(key_node)
        if key is None:
            _warn(self.source_name, node.lineno, f"non-literal key {self._excerpt(node)}; skipped.")
            return

        variant: str | None = None

        if variant_node is not None:
            variant = _literal_string(variant_node)
            if variant is None:
                _warn(self.source_name, node.lineno, f'non-literal context {self._excerpt(node)} for key "{key}"; extracted with no variant.')

        for keyword in kwargs:
            if keyword.key not in VARIANT_KEYWORDS:
                continue
            if not (isinstance(keyword.value, nodes.Const) and isinstance(keyword.value.value, str)):
                _warn(self.source_name, node.lineno, f'non-literal _variant for key "{key}"; extracted with no variant.')
                continue
            variant = keyword.value.value

        self.keys.add((key, variant))

    def _excerpt(self, node: nodes.Node) -> str:
        """
        Return a short, single-line excerpt of the source at the node's line.

        Jinja has no equivalent of ``ast.unparse`` for its nodes, and the source
        line is what a developer needs to see anyway.
        """
        lineno = node.lineno
        if 1 <= lineno <= len(self._lines):
            excerpt = self._lines[lineno - 1].strip()
            if excerpt:
                return excerpt if len(excerpt) <= 60 else f"{excerpt[:57]}..."
        return f"a translation call on line {lineno}"


class JinjaExtractor:
    """
    Collect ``(key, variant)`` pairs from Jinja templates.

    The extractor parses templates with the same environment the application
    renders with, so custom delimiters, custom extensions and ``{% raw %}``
    blocks are all handled the way the application experiences them.
    """

    suffixes: tuple[str, ...] = DEFAULT_TEMPLATE_SUFFIXES

    def __init__(self, environment: Environment | None = None, config: JinjaConfig | None = None) -> None:
        """
        Initialize the extractor.

        Args:
            environment: The environment used to parse templates. A default one
                with the helpers installed is used when omitted.
            config: The names to look for. Read from the environment when
                omitted.
        """
        self.environment = environment if environment is not None else build_default_environment()
        self.config = config if config is not None else get_jinja_config(self.environment)

    def handles(self, path: Path) -> bool:
        """
        Return whether this extractor is responsible for a file.
        """
        return has_suffix(path, self.suffixes)

    def extract(self, path: Path) -> set[ExtractedKey]:
        """
        Parse a template file and return the collected pairs.

        A template that cannot be read or parsed is reported as a warning and
        yields no keys, so a broken template never blocks extraction.
        """
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            _warn(str(path), 0, f"could not read template: {exc}")
            return set()

        try:
            template = self.environment.parse(source, name=str(path), filename=str(path))
        except TemplateSyntaxError as exc:
            _warn(str(path), exc.lineno or 0, f"could not parse template: {exc.message}")
            return set()

        return TemplateCallVisitor(self.config, str(path), source).visit(template)
