"""Shared leaf helpers: the guard code registry and `where` formatting."""

from __future__ import annotations

import re
from typing import Any

from .problems import Problem
from .scan import scan_string

GUARD_CODES: frozenset[str] = frozenset({
    "schema-missing", "schema-unknown", "section-missing", "field-missing", "field-invalid",
    "field-unknown", "id-duplicate", "layer-undeclared", "path-invalid", "path-missing",
    "glob-empty", "line-invalid", "edge-dangling", "edge-self", "node-orphan",
    "step-node-missing", "flow-too-short",
    "coverage-core-empty", "coverage-core-glob-empty", "coverage-uncovered",
    "coverage-ignore-no-why", "coverage-ignore-unused",
    "secret-suspect", "secret-allow-no-why", "secret-allow-unused",
})


def _problem(code: str, where: str, message: str) -> Problem:
    if code not in GUARD_CODES:  # a programming error, never caused by map content
        raise AssertionError(f"unregistered guard code {code!r}")
    return Problem(code, where or "$", message)


def _redact(text: str) -> str:
    """A suspect value cut to its first 4 characters, never the whole of it."""
    return text[:4] + "…"


def _quote(key: str) -> str:
    """A key as it appears inside a message: `repr`, or redacted when it looks like a secret."""
    return repr(_redact(key)) if scan_string(key) else repr(key)


def _join(where: str, key: str) -> str:
    return f"{where}.{key}" if where else key


_SAFE_ID = re.compile(r"[A-Za-z0-9._:-]+")


def _ident(obj: Any, index: int) -> str:
    """Address an object by its id when it is a plain token, otherwise by index."""
    if isinstance(obj, dict):
        value = obj.get("id")
        if isinstance(value, str) and _SAFE_ID.fullmatch(value) and not scan_string(value):
            return value
    return str(index)


def _seg(key: str) -> str:
    """A key or section name as a `where` segment, with control characters escaped."""
    if scan_string(key):
        return _redact(key)
    return key if _SAFE_ID.fullmatch(key) else ascii(key)
