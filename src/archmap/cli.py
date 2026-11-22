"""Command line interface: `archmap check` and `archmap build`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from ._version import __version__
from .guard import check_map
from .loader import MapLoadError, load_map
from .render import render_html

DEFAULT_MAP = Path("docs") / "architecture-map.json"
DEFAULT_OUT = Path("runtime") / "html-artifacts" / "architecture-map.html"
UNRENDERABLE = ("schema-missing", "schema-unknown")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="archmap", description="Guard a project's architecture map.")
    parser.add_argument("--version", action="version", version=f"archmap {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    check = sub.add_parser("check", help="check the map against the code")
    check.add_argument("map", nargs="?", metavar="MAP", help="map file (default: <root>/docs/architecture-map.json)")
    check.add_argument("--root", default=".", metavar="DIR", help="project root (default: current directory)")
    build = sub.add_parser("build", help="build the offline HTML viewer")
    build.add_argument("map", nargs="?", metavar="MAP", help="map file (default: <root>/docs/architecture-map.json)")
    build.add_argument("-o", "--output", metavar="OUT", help="output file (default: <root>/runtime/html-artifacts/architecture-map.html)")
    build.add_argument("--root", default=".", metavar="DIR", help="project root (default: current directory)")
    return parser


def _load_and_check(args: argparse.Namespace):
    """Resolve root and map, load and check it; returns (data, problems) or an exit code."""
    root = Path(args.root)
    if not root.is_dir():
        print(f"archmap: root {args.root!r} is not a directory", file=sys.stderr)
        return 2
    map_path = Path(args.map) if args.map else root / DEFAULT_MAP
    try:
        data = load_map(map_path)
    except MapLoadError as exc:
        print(exc.problem, file=sys.stderr)
        return 2
    return data, check_map(data, root)


def _cmd_check(args: argparse.Namespace) -> int:
    loaded = _load_and_check(args)
    if isinstance(loaded, int):
        return loaded
    _, problems = loaded
    for problem in problems:
        print(problem)
    print(f"{len(problems)} problem(s)" if problems else "no problems", file=sys.stderr)
    return 1 if problems else 0


def _cmd_build(args: argparse.Namespace) -> int:
    loaded = _load_and_check(args)
    if isinstance(loaded, int):
        return loaded
    data, problems = loaded
    for problem in problems:
        print(problem)
    if any(p.code in UNRENDERABLE for p in problems):
        print("not an archmap/1 map, nothing to render", file=sys.stderr)
        return 1
    out = Path(args.output) if args.output else Path(args.root) / DEFAULT_OUT
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_html(data, problems), encoding="utf-8", newline="\n")
    except (OSError, UnicodeError) as exc:
        print(f"archmap: cannot write {str(out)!r}: {exc}", file=sys.stderr)
        return 2
    print(f"{len(problems)} problem(s)" if problems else "no problems", file=sys.stderr)
    print(f"wrote {out}", file=sys.stderr)
    return 1 if problems else 0


def main(argv: Optional[list] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    if args.command == "check":
        return _cmd_check(args)
    if args.command == "build":
        return _cmd_build(args)
    parser.print_usage(sys.stderr)
    return 2
