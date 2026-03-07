# Configuration file for the Sphinx documentation builder.

import os
import re
import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, os.path.abspath('..'))


def _read_setup_metadata():
    root = Path(__file__).resolve().parents[1]
    setup_py = root / "setup.py"
    text = setup_py.read_text(encoding="utf-8", errors="replace")

    def _match(field, default):
        m = re.search(rf'\b{field}\s*=\s*["\']([^"\']+)["\']', text)
        return m.group(1) if m else default

    return {
        "name": _match("name", "hermax"),
        "version": _match("version", "0.0.0"),
    }


_SETUP_META = _read_setup_metadata()

# -- Project information -----------------------------------------------------
project = _SETUP_META["name"]
copyright = f'{datetime.now().year}, Josep Maria Salvia Hornos'
author = 'Josep Maria Salvia Hornos'
version = _SETUP_META["version"]
release = _SETUP_META["version"]

# -- General configuration ---------------------------------------------------
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx.ext.napoleon',
    'myst_parser',
]

# Allow API docs to render even when native solver extensions are unavailable
# in the doc build environment.
autodoc_mock_imports = [
    'hermax.core.urmaxsat_py',
    'hermax.core.urmaxsat_comp_py',
    'hermax.core.cashwmaxsat',
    'hermax.core.evalmaxsat_latest',
    'hermax.core.evalmaxsat_incr',
    'hermax.core.openwbo',
    'hermax.core.openwbo_inc',
    'hermax.internal._pblib',
    'hermax_pycard',
    'fast_wcnf_loader_capi',
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']
language = 'en'

# -- Options for HTML output -------------------------------------------------
html_theme = 'pydata_sphinx_theme'
html_static_path = ['_static']
html_css_files = ['custom.css']
html_logo = "../images/banner.png"
html_favicon = "../images/favicon.png"
html_show_sourcelink = False

html_theme_options = {
    "logo": {
        "text": "", # No text, just logo
    },
    "show_prev_next": False,
    "navbar_start": ["navbar-logo"],
    "navbar_center": ["navbar-nav"],
    "navbar_end": ["theme-switcher", "navbar-icon-links"],
    "header_links_before_dropdown": 8,
}

# LaTeX (pdf) build: keep Unicode symbols in autodoc/docstrings without editing source code.
latex_elements = {
    "preamble": r"""
\DeclareUnicodeCharacter{2228}{\ensuremath{\lor}}
\DeclareUnicodeCharacter{2227}{\ensuremath{\land}}
\DeclareUnicodeCharacter{00AC}{\ensuremath{\lnot}}
\DeclareUnicodeCharacter{2264}{\ensuremath{\le}}
\DeclareUnicodeCharacter{2265}{\ensuremath{\ge}}
\DeclareUnicodeCharacter{2194}{\ensuremath{\leftrightarrow}}
\DeclareUnicodeCharacter{2192}{\ensuremath{\rightarrow}}
\DeclareUnicodeCharacter{21D2}{\ensuremath{\Rightarrow}}
\DeclareUnicodeCharacter{2208}{\ensuremath{\in}}
\DeclareUnicodeCharacter{2286}{\ensuremath{\subseteq}}
\DeclareUnicodeCharacter{2282}{\ensuremath{\subset}}
\DeclareUnicodeCharacter{2211}{\ensuremath{\sum}}
\DeclareUnicodeCharacter{2200}{\ensuremath{\forall}}
\DeclareUnicodeCharacter{2203}{\ensuremath{\exists}}
\DeclareUnicodeCharacter{2260}{\ensuremath{\neq}}
\DeclareUnicodeCharacter{00B1}{\ensuremath{\pm}}
""",
}

# Ensure methods are documented
autodoc_default_options = {
    'members': True,
    'member-order': 'bysource',
    'undoc-members': True,
    'exclude-members': '__weakref__'
}

autosummary_generate = True
autodoc_class_signature = 'separated'
autodoc_typehints = 'description'
