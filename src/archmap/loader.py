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
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise MapLoadError(
            Problem("json-invalid", f"{where}:{exc.lineno}:{exc.colno}", f"invalid JSON: {exc.msg}")
        ) from exc
    except (RecursionError, ValueError) as exc:
        raise MapLoadError(
            Problem("json-invalid", where, "map cannot be parsed (too deeply nested or a number is too large)")
        ) from exc
