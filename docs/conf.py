"""Configure the generated SRD Arena documentation site."""

from importlib import import_module

project = "SRD Arena"
author = "Alessandro La Perna"
release = "0.1.0"

# Load the documented facades once. Several content facades share Pydantic base
# models, and keeping their canonical module objects avoids reconstructing those
# models while autodoc traverses the reference page.
for module_name in (
    "srd_arena.engine.api",
    "srd_arena.content.capabilities",
    "srd_arena.content.creatures",
    "srd_arena.content.encounters",
    "srd_arena.content.equipment",
    "srd_arena.content.spells",
    "srd_arena.domain.capabilities",
    "srd_arena.domain.creatures",
    "srd_arena.domain.effects",
    "srd_arena.domain.equipment",
    "srd_arena.domain.geometry",
    "srd_arena.domain.rolls",
    "srd_arena.domain.encounters",
    "srd_arena.domain.spells",
):
    import_module(module_name)

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.doctest",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}
exclude_patterns = ["_build", ".venv", "__pycache__"]

autodoc_member_order = "bysource"
autodoc_typehints = "description"
doctest_test_doctest_blocks = "default"

html_theme = "furo"
html_title = "SRD Arena Documentation"
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_theme_options = {
    "light_css_variables": {
        "color-brand-primary": "#8a3f2d",
        "color-brand-content": "#8a3f2d",
    },
    "dark_css_variables": {
        "color-brand-primary": "#e7a47f",
        "color-brand-content": "#e7a47f",
    },
}
