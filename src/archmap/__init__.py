"""archmap: guard a project's architecture map and build an offline viewer."""

from .loader import MapLoadError, load_map
from .problems import Problem

__version__ = "0.1.0.dev0"

__all__ = ["__version__", "Problem", "MapLoadError", "load_map"]
