import importlib.util
import os
import subprocess
import tempfile
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DIST_FILE = ROOT / "dist" / "archmap.py"


def _impl() -> str:
    return os.environ.get("ARCHMAP_IMPL", "package")


@pytest.fixture
def dist_bundle():
    """The loaded `dist/archmap.py` module (only in ARCHMAP_IMPL=dist mode)."""
    if _impl() != "dist":
        pytest.skip("needs ARCHMAP_IMPL=dist")
    if not DIST_FILE.is_file():
        pytest.fail(f"ARCHMAP_IMPL=dist but {DIST_FILE} is missing; run tools/build_single.py first")
    # an editable install may already be imported; the bundle must be the only archmap
    for name in [n for n in sys.modules if n == "archmap" or n.startswith("archmap.")]:
        del sys.modules[name]
    spec = importlib.util.spec_from_file_location("archmap_dist", DIST_FILE)
    module = importlib.util.module_from_spec(spec)
    sys.modules["archmap_dist"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def am(request):
    """Module exposing the public API, from the package or the bundled dist file."""
    if _impl() != "dist":
        import archmap

        return archmap
    request.getfixturevalue("dist_bundle")
    mod = sys.modules["archmap"]
    assert getattr(mod, "__bundled__", False) is True
    return mod


@pytest.fixture
def run_cli():
    """Run the CLI in a subprocess: `python -m archmap` or `python dist/archmap.py`."""

    def _run(args, cwd=None):
        if _impl() == "dist":
            # isolated, no site: the installed package must not be importable
            cmd = [sys.executable, "-I", "-S", str(DIST_FILE), *args]
            cwd = cwd or tempfile.gettempdir()  # never run from inside the repo
        else:
            cmd = [sys.executable, "-m", "archmap", *args]
        return subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8"
        )

    return _run
