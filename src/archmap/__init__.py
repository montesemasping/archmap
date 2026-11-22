"""archmap: guard a project's architecture map and build an offline viewer."""

from ._version import __version__
from . import guard, paths, render
from .cli import main
from .guard import check_map
from .loader import MapLoadError, load_map
from .problems import Problem
from .render import render_html, source_link
from .secrets import find_secrets

__all__ = ["__version__", "Problem", "MapLoadError", "load_map", "paths", "guard", "check_map", "render", "render_html", "source_link", "find_secrets", "main"]
