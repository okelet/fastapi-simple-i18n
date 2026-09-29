r"""
A minimal web UI for reviewing and editing translation files.

The UI points at a directory of locale JSON files (one per locale, the format
this library reads and writes) and lets a translator browse them, filter the
entries and edit a translation, its variant and its draft flag without leaving
the browser.

Its dependencies live in the ``web`` dependency group, so run it with::

    uv sync --group web
    FSI_WEB_TRANSLATIONS_DIR=/path/to/translations \\
        uv run --group web uvicorn fastapi_simple_i18n.web.app:app

Like the rest of this package it exposes no top-level re-exports; import from
the submodules directly::

    from fastapi_simple_i18n.web.app import create_app
    from fastapi_simple_i18n.web.config import Settings
"""
