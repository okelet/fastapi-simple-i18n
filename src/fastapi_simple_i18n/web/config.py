"""
Settings for the translation web UI, read from environment variables.

Every setting is prefixed with ``FSI_WEB_``. The only required one in practice
is ``FSI_WEB_TRANSLATIONS_DIR``, the directory holding the locale JSON files the
UI manages; it defaults to ``./translations``.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Web UI configuration loaded from environment variables with the ``FSI_WEB_`` prefix.

    Attributes:
        translations_dir: Directory holding one JSON file per locale. May not exist
            yet; the locales page then explains what is missing instead of failing.
        page_size: Number of entries shown per page in the strings table.
        site_title: Title shown in the navigation bar and the browser tab.
    """

    model_config = SettingsConfigDict(
        env_prefix="FSI_WEB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    translations_dir: Path = Path("./translations")
    page_size: int = 50
    site_title: str = "Translations"

    @field_validator("translations_dir", mode="after")
    @classmethod
    def expand_translations_dir(cls, value: Path) -> Path:
        """
        Expand ``~`` and make the path absolute.

        An absolute path keeps the "not found" hint on the locales page
        unambiguous regardless of the process working directory.
        """
        return value.expanduser().absolute()


@lru_cache
def get_settings() -> Settings:
    """
    Return the cached settings singleton.
    """
    return Settings()
