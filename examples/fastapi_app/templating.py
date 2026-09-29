"""
Template environment for the example application.

The environment is created here, in its own module, so that both the FastAPI
app (:mod:`examples.fastapi_app.main`) and the translation module
(:mod:`examples.fastapi_app.i18n`) can reach the *same* environment. That is
what lets the extraction script find the strings with the very names and
delimiters the application renders with.
"""

from pathlib import Path

from fastapi.templating import Jinja2Templates

from fastapi_simple_i18n.jinja import install_translation_support

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

# Adds t(), the t filter, {% trans %} blocks and the formatting helpers.
install_translation_support(templates.env)
