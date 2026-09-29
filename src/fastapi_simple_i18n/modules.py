"""
Base class for registrable translation modules.

A translation module tells the system two things: where its source code lives
(so translatable strings can be extracted from it) and where its per-locale
translation files live (so they can be loaded at runtime).
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - Jinja2 is an optional dependency
    from jinja2 import Environment

# Default file suffixes scanned for Jinja templates. Compound suffixes such as
# ".html.j2" are matched against the whole file name, not against
# ``pathlib.Path.suffix``, which only ever returns the last one.
DEFAULT_TEMPLATE_SUFFIXES = (".jinja", ".jinja2", ".html", ".html.j2", ".j2.html")


def has_suffix(path: Path, suffixes: tuple[str, ...]) -> bool:
    """
    Return whether a file name ends with one of the given suffixes.

    The match is on the file name and is case-insensitive, so compound suffixes
    work: ``page.html.j2`` is matched by ``.html.j2`` even though
    ``path.suffix`` would only ever report ``.j2``. An empty tuple matches
    nothing, which lets a module opt out of a kind of file without special cases.

    Args:
        path: The file to test.
        suffixes: The suffixes to accept, in lowercase.
    """
    name = path.name.lower()
    return any(name.endswith(suffix) for suffix in suffixes)


class BaseModuleTranslation(ABC):
    """
    Abstract base class describing a translatable module.

    Subclasses point the system at the directories to scan for translatable
    strings and at the directory that holds the locale files. A typical module
    simply returns the directory containing its own package, but a module may
    span several source directories.

    Example:
        ::

            from pathlib import Path

            from fastapi_simple_i18n.modules import BaseModuleTranslation


            class MyModuleTranslation(BaseModuleTranslation):

                @classmethod
                def get_source_dirs(cls) -> list[Path]:
                    return [Path(__file__).parent]

                @classmethod
                def get_translation_dir(cls) -> Path:
                    return Path(__file__).parent / "translations"
    """

    @classmethod
    @abstractmethod
    def get_source_dirs(cls) -> list[Path]:
        """
        Return the directories to scan for translatable strings.

        Most modules return the directory of their own package, but this can be
        any number of directories.
        """
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def get_translation_dir(cls) -> Path:
        """
        Return the directory holding one JSON file per locale.

        For example a directory containing ``es.json`` and ``fr.json``.
        """
        raise NotImplementedError

    @classmethod
    def discover_locales(cls) -> list[str]:
        """
        Discover available locales from the JSON files in the translation dir.

        Returns the sorted list of file stems (e.g. ``["es", "fr"]``). Returns
        an empty list if the directory does not exist.
        """
        translation_dir = cls.get_translation_dir()
        if not translation_dir.is_dir():
            return []
        return sorted(path.stem for path in translation_dir.glob("*.json"))

    @classmethod
    def get_translation_file(cls, locale: str) -> Path:
        """
        Return the path to the JSON file for a given locale.
        """
        return cls.get_translation_dir() / f"{locale}.json"

    # --- Templates ---

    @classmethod
    def get_template_dirs(cls) -> list[Path]:
        """
        Return the directories holding Jinja templates to scan.

        Defaults to no directories, since a module with no templates is the
        common case and Jinja2 is an optional dependency. A module with
        templates overrides this so the extraction script parses them.
        """
        return []

    @classmethod
    def get_template_suffixes(cls) -> tuple[str, ...]:
        """
        Return the file suffixes treated as Jinja templates.

        Defaults to :data:`DEFAULT_TEMPLATE_SUFFIXES`. Suffixes are matched
        against the whole file name, so a compound one like ``".html.j2"`` works.
        """
        return DEFAULT_TEMPLATE_SUFFIXES

    @classmethod
    def get_jinja_environment(cls) -> Environment | None:
        """
        Return the Jinja environment used to parse this module's templates.

        Returning ``None`` (the default) makes the extraction script use a
        plain environment with the translation helpers installed.

        Override this and return the *same* environment the application renders
        with when it is configured, so the extraction sees the real delimiters,
        extensions and ``{% raw %}`` blocks, and the real names of the
        translation function and filter.
        """
        return None
