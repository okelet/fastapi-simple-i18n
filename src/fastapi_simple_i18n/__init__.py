"""
fastapi-simple-i18n — simple, module-friendly i18n for FastAPI and CLI scripts.

This package intentionally exposes no top-level re-exports. Import the public
API directly from the submodules, for example::

    from fastapi_simple_i18n.helpers import t, t_number, t_date
    from fastapi_simple_i18n.manager import TranslationManager
    from fastapi_simple_i18n.middleware import TranslationMiddleware
    from fastapi_simple_i18n.modules import BaseModuleTranslation
    from fastapi_simple_i18n.registry import get_translation_manager, set_translation_manager
    from fastapi_simple_i18n.locale import get_current_locale, set_current_locale
"""
