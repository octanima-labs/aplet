from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

project = 'Aplet'
author = 'octanima-labs'
copyright = '2026, octanima-labs'
release = '0.1.0'

extensions = [
    'myst_parser',
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx.ext.napoleon',
    'sphinx_autodoc_typehints',
    'sphinx_copybutton',
]

source_suffix = {
    '.rst': 'restructuredtext',
    '.md': 'markdown',
}
master_doc = 'index'
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']
templates_path = ['_templates']

html_theme = 'pydata_sphinx_theme'
html_title = 'Aplet'
html_static_path = ['_static']
html_css_files = ['aplet-logo.css']
html_sidebars = {
    '**': [],
}
html_theme_options = {
    'github_url': 'https://github.com/octanima-labs/aplet',
    'logo': {
        'image_light': 'icon.png',
        'image_dark': 'icon.png',
        'alt_text': 'Aplet',
    },
    'navbar_align': 'left',
    'navbar_start': ['aplet-navbar-logo'],
    'primary_sidebar_end': [],
    'show_toc_level': 2,
}

autodoc_default_options = {
    'undoc-members': False,
    'show-inheritance': True,
}
autodoc_typehints = 'description'
autodoc_member_order = 'bysource'
autosummary_generate = False
napoleon_google_docstring = True
napoleon_numpy_docstring = False
myst_heading_anchors = 3
