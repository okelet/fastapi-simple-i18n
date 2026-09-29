"""
The translation manager.

The :class:`TranslationManager` is the central registry. It holds the loaded
:class:`~fastapi_simple_i18n.models.Translation` objects per locale, knows the
built-in locale (the language the source strings are written in), and resolves
keys with variant, draft, built-in, and fallback logic.
"""

import logging

from .models import Translation, TranslationEntry
from .modules import BaseModuleTranslation

logger = logging.getLogger(__name__)


class TranslationManager:
    """
    Registry and resolver for translations.

    The manager stores one :class:`Translation` per locale and resolves a key
    (with an optional variant) to a final string for a target locale.

    Resolution rules for :meth:`translate`:

    1. If the target locale equals the built-in locale, the key is returned
       verbatim (the source strings are already in that language). The variant
       is ignored in this case.
    2. Otherwise, the matching entry ``(key, variant)`` is looked up in the
       locale's :class:`Translation`. Draft entries are used as-is.
    3. If no entry is found, the key itself is returned as a fallback and a
       warning is logged.
    """

    def __init__(self, builtin_locale: str = "en") -> None:
        """
        Initialize an empty manager.

        Args:
            builtin_locale: The language the source strings are written in. For
                this locale no translation files are needed.
        """
        self.builtin_locale = builtin_locale
        self._translations: dict[str, Translation] = {}

    # --- Registration ---

    def add_translation(self, translation: Translation) -> None:
        """
        Register (or merge) a :class:`Translation` for its locale.

        If a translation for the same locale already exists, the new entries
        are merged into it (later entries overwrite earlier ones).
        """
        existing = self._translations.get(translation.locale)
        if existing is None:
            self._translations[translation.locale] = translation
            return
        for entry in translation.entries():
            existing.add(entry)

    def add_entries(self, locale: str, entries: list[TranslationEntry]) -> None:
        """
        Register a list of entries for a locale.

        Convenience wrapper around :meth:`add_translation` useful for CLI
        scripts and tests that build entries by hand.
        """
        self.add_translation(Translation.from_entries(locale, entries))

    def register_translation(self, module: type[BaseModuleTranslation]) -> None:
        """
        Register all locale files exposed by a translation module.

        Discovers the module's locales (from the JSON files in its translation
        directory) and loads each one into the manager. Locales equal to the
        built-in locale are skipped, since they need no file.

        Args:
            module: A :class:`BaseModuleTranslation` subclass (the class itself,
                not an instance).
        """
        translation_dir = module.get_translation_dir()
        for locale in module.discover_locales():
            if locale == self.builtin_locale:
                continue
            path = translation_dir / f"{locale}.json"
            self.add_translation(Translation.from_file(locale, path))
            logger.debug("Registered locale %s from %s", locale, path)

    # --- Introspection ---

    def get_translation(self, locale: str) -> Translation | None:
        """
        Return the :class:`Translation` registered for a locale, if any.
        """
        return self._translations.get(locale)

    def supported_locales(self) -> set[str]:
        """
        Return the set of locales the manager can serve.

        Always includes the built-in locale.
        """
        return {self.builtin_locale, *self._translations.keys()}

    # --- Resolution ---

    def translate(self, key: str, variant: str | None = None, locale: str | None = None) -> str:
        """
        Resolve a key (and optional variant) to a translated string.

        Args:
            key: The source string to translate.
            variant: Optional variant to disambiguate identical keys.
            locale: Target locale. When ``None`` the caller is expected to have
                resolved it already; callers usually pass the current locale.

        Returns:
            The translated string, or the key itself as a fallback.
        """
        target_locale = locale or self.builtin_locale

        # Built-in locale: source strings are already in this language.
        if target_locale == self.builtin_locale:
            return key

        translation = self._translations.get(target_locale)
        if translation is not None:
            entry = translation.get(key, variant)
            if entry is not None:
                return entry.value

        if variant is not None:
            logger.warning("Missing translation for key=%r variant=%r locale=%r", key, variant, target_locale)
        else:
            logger.warning("Missing translation for key=%r locale=%r", key, target_locale)
        return key
