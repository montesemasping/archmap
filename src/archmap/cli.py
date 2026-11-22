"""Command line interface: `archmap check`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from . import __version__
from .guard import check_map
from .loader import MapLoadError, load_map

DEFAULT_MAP = Path("docs") / "architecture-map.json"


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):  # argparse exits with 2 on usage errors already
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: {message}\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="archmap", description="Guard a project's architecture map.")
    parser.add_argument("--version", action="version", version=f"archmap {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    check = sub.add_parser("check", help="check the map against the code")
    check.add_argument("map", nargs="?", metavar="MAP", help="map file (default: <root>/docs/architecture-map.json)")
    check.add_argument("--root", default=".", metavar="DIR", help="project root (default: current directory)")
    return parser


def _cmd_check(args: argparse.Namespace) -> int:
    root = Path(args.root)
    map_path = Path(args.map) if args.map else root / DEFAULT_MAP
    try:
        data = load_map(map_path)
    except MapLoadError as exc:
        print(exc.problem, file=sys.stderr)
        return 2
    problems = check_map(data, root)
    for problem in problems:
        print(problem)
    print(f"{len(problems)} problem(s)" if problems else "no problems", file=sys.stderr)
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
    parser.print_usage(sys.stderr)
    return 2
