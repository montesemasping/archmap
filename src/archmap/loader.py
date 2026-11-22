"""Load the architecture map JSON file."""

from __future__ import annotations

import json
import os
from typing import Any

from .problems import Problem


class MapLoadError(Exception):
    def __init__(self, problem: Problem) -> None:
        super().__init__(str(problem))
        self.problem = problem


class _NonStandardJson(Exception):
    """Raised from parser hooks for input that is not portable JSON."""


def _reject_constant(name: str) -> Any:
    raise _NonStandardJson(f"{name} is not valid JSON")


def _reject_duplicates(pairs: list) -> dict:
    seen: dict = {}
    for key, value in pairs:
        if key in seen:
            raise _NonStandardJson(f"duplicate key {key!r}")
        seen[key] = value
    return seen


MAX_DEPTH = 200


def _too_deep(value: Any) -> bool:
    """Is the nesting of lists and objects deeper than MAX_DEPTH? Iterative, so it cannot recurse."""
    stack = [(value, 1)]
    while stack:
        item, depth = stack.pop()
        if isinstance(item, dict):
            children = item.values()
        elif isinstance(item, list):
            children = item
        else:
            continue
        if depth > MAX_DEPTH:
            return True
        stack.extend((child, depth + 1) for child in children)
    return False


def load_map(path: str | os.PathLike) -> Any:
    """Read the map as UTF-8 (BOM allowed) and parse it. The root may be any JSON value."""
    where = os.fspath(path)
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except (OSError, ValueError) as exc:
        detail = getattr(exc, "strerror", None) or exc
        raise MapLoadError(
            Problem("map-missing", where, f"cannot read map file: {detail}")
        ) from exc
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise MapLoadError(
            Problem("json-invalid", where, f"file is not valid UTF-8: {exc.reason}")
        ) from exc
    too_deep = Problem("json-invalid", where, f"nesting deeper than {MAX_DEPTH}")
    try:
        data = json.loads(text, parse_constant=_reject_constant, object_pairs_hook=_reject_duplicates)
    except _NonStandardJson as exc:
        raise MapLoadError(Problem("json-invalid", where, f"invalid JSON: {exc}")) from exc
    except json.JSONDecodeError as exc:
        raise MapLoadError(
            Problem("json-invalid", f"{where}:{exc.lineno}:{exc.colno}", f"invalid JSON: {exc.msg}")
        ) from exc
    except RecursionError as exc:
        raise MapLoadError(too_deep) from exc
    except ValueError as exc:
        raise MapLoadError(Problem("json-invalid", where, "map cannot be parsed (a number is too large)")) from exc
    if _too_deep(data):
        raise MapLoadError(too_deep)
    return data
