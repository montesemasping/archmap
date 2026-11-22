"""archmap: guard a project's architecture map and build an offline viewer."""

__version__ = "0.1.0.dev0"

from . import paths  # noqa: E402
from .cli import main  # noqa: E402
from .guard import check_map  # noqa: E402
from .loader import MapLoadError, load_map  # noqa: E402
from .problems import Problem  # noqa: E402

__all__ = ["__version__", "Problem", "MapLoadError", "load_map", "paths", "check_map", "main"]
