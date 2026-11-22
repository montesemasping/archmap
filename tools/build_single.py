"""Build the single-file distribution `dist/archmap.py` from `src/archmap/`.

Stdlib only. The output is deterministic: same sources, same bytes (UTF-8, LF).

    python tools/build_single.py [-o OUTPUT]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "src" / "archmap"
DEFAULT_OUT = ROOT / "dist" / "archmap.py"

# `__main__` is the `python -m` entry point; the bundle has its own.
SKIP = {"__main__.py"}

BUNDLE_MODULE_TEMPLATE = (
    '"""Template of the offline viewer, embedded by tools/build_single.py."""\n\nTEMPLATE = {template}\n'
)

LOADER = '''
import importlib.abc
import importlib.util
import sys


class _BundleFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Serves the embedded `archmap` modules; claims no other name."""

    _archmap_bundle = True

    def find_spec(self, fullname, path=None, target=None):
        if fullname not in _SOURCES:
            return None
        return importlib.util.spec_from_loader(fullname, self, is_package=fullname == "archmap")

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        # The import system has already put `module` into sys.modules, as @dataclass needs.
        name = module.__spec__.name
        exec(compile(_SOURCES[name], "<archmap-bundle>/" + name, "exec"), module.__dict__)


# Drop stale copies (an installed package, an earlier load of this file) so the bundle wins.
for _name in [n for n in sys.modules if n == "archmap" or n.startswith("archmap.")]:
    del sys.modules[_name]
sys.meta_path[:] = [f for f in sys.meta_path if not getattr(f, "_archmap_bundle", False)]
sys.meta_path.insert(0, _BundleFinder())

import archmap  # noqa: E402

archmap.__bundled__ = True
from archmap import *  # noqa: E402,F401,F403
from archmap import __version__, main  # noqa: E402,F401

if __name__ == "__main__":
    sys.exit(main())
'''


def read_text(path: Path) -> str:
    """Read UTF-8 with LF line endings, whatever the checkout did to them."""
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def package_version() -> str:
    match = re.search(r'__version__\s*=\s*"([^"]+)"', read_text(PKG / "_version.py"))
    if not match:
        raise SystemExit("cannot read the version from src/archmap/_version.py")
    return match.group(1)


def module_name(path: Path) -> str:
    return "archmap" if path.name == "__init__.py" else f"archmap.{path.stem}"


def build() -> str:
    version = package_version()
    sources = {module_name(p): read_text(p) for p in sorted(PKG.glob("*.py")) if p.name not in SKIP}
    sources["archmap._bundled"] = BUNDLE_MODULE_TEMPLATE.format(template=repr(read_text(PKG / "template.html")))
    entries = "".join(f"    {name!r}: {sources[name]!r},\n" for name in sorted(sources))
    return (
        f"# archmap {version} – single-file build. DO NOT EDIT; built from archmap v{version}.\n"
        "# Usage: python archmap.py check | build | --version   (stdlib only, Python 3.10+)\n"
        f"__bundled__ = True\n\n_SOURCES = {{\n{entries}}}\n"
        f"{LOADER}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the single-file archmap distribution.")
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUT, help=f"output file (default: {DEFAULT_OUT})")
    args = parser.parse_args(argv)
    text = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print(f"wrote {args.output} ({len(text.encode('utf-8'))} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
