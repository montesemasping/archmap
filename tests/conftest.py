import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DIST_FILE = ROOT / "dist" / "archmap.py"


def _impl() -> str:
    return os.environ.get("ARCHMAP_IMPL", "package")


@pytest.fixture
def am():
    """Module exposing the public API, from the package or the bundled dist file."""
    if _impl() != "dist":
        import archmap

        return archmap
    if not DIST_FILE.is_file():
        pytest.skip(f"ARCHMAP_IMPL=dist but {DIST_FILE} is missing; build it first")
    spec = importlib.util.spec_from_file_location("archmap_dist", DIST_FILE)
    module = importlib.util.module_from_spec(spec)
    sys.modules["archmap_dist"] = module
    spec.loader.exec_module(module)
    mod = sys.modules["archmap"]
    assert getattr(mod, "__bundled__", False) is True
    return mod


@pytest.fixture
def run_cli():
    """Run the CLI in a subprocess: `python -m archmap` or `python dist/archmap.py`."""

    def _run(args, cwd=None):
        if _impl() == "dist":
            cmd = [sys.executable, str(DIST_FILE), *args]
        else:
            cmd = [sys.executable, "-m", "archmap", *args]
        return subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8"
        )

    return _run
