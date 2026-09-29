"""
Translation module definition for the example application.

This class tells fastapi-simple-i18n where the example app's source code,
templates and translation files live. It is also the argument you pass to the
extraction script::

    python -m fastapi_simple_i18n.extract_translations examples.fastapi_app.i18n:AppTranslation
"""

from pathlib import Path

from jinja2 import Environment

from fastapi_simple_i18n.modules import BaseModuleTranslation

from .templating import templates


class AppTranslation(BaseModuleTranslation):
    """
    Translation module for the example FastAPI application.
    """

    @classmethod
    def get_source_dirs(cls) -> list[Path]:
        """
        Return the directory of the example application package.
        """
        return [Path(__file__).parent]

    @classmethod
    def get_translation_dir(cls) -> Path:
        """
        Return the ``translations`` directory next to this package.
        """
        return Path(__file__).parent / "translations"

    @classmethod
    def get_template_dirs(cls) -> list[Path]:
        """
        Return the ``templates`` directory next to this package.
        """
        return [Path(__file__).parent / "templates"]

    @classmethod
    def get_jinja_environment(cls) -> Environment:
        """
        Return the very environment the example application renders with.

        Returning it here is what lets the extraction script see the real
        translation function and filter names and the real Jinja configuration.
        """
        return templates.env
