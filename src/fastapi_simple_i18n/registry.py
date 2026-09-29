"""
Global access to the active translation manager.

The active :class:`~fastapi_simple_i18n.manager.TranslationManager` is a
process-wide singleton (it is shared across all requests). The FastAPI
middleware sets it at construction time, and CLI scripts can set it manually so
that ``t()`` and friends work without a web server.

Only the *locale* is per-request; that lives in a
:class:`contextvars.ContextVar` (see :mod:`fastapi_simple_i18n.locale`).
"""

from .manager import TranslationManager

# Process-wide active manager. ``None`` means no manager has been configured.
_current_manager: TranslationManager | None = None  # pylint: disable=invalid-name


def set_translation_manager(manager: TranslationManager) -> None:
    """
    Set the active translation manager for the process.

    Called by the FastAPI middleware at construction time, or manually from CLI
    scripts and tests.
    """
    global _current_manager  # noqa: PLW0603  # pylint: disable=global-statement
    _current_manager = manager


def get_translation_manager() -> TranslationManager:
    """
    Return the active translation manager.

    Raises:
        RuntimeError: If no manager has been configured. Configure one by adding
            the FastAPI middleware or by calling :func:`set_translation_manager`.
    """
    if _current_manager is None:
        raise RuntimeError(
            "No TranslationManager configured. Add TranslationMiddleware to your "
            "FastAPI app or call set_translation_manager() before using t().",
        )
    return _current_manager


def has_translation_manager() -> bool:
    """
    Return whether an active translation manager is configured.
    """
    return _current_manager is not None
