"""Detect secret-looking strings in the map. Only string values are scanned."""

from __future__ import annotations

import re
from typing import Any

from .problems import Problem
from .scan import _hint, entropy, scan_string  # noqa: F401  (entropy is re-exported)
from .schema import SECRET_ALLOW_MIN_MATCH
from .where import _ident, _join, _problem, _seg


def _suppressed(text: str, span: tuple[int, int], allow: list[tuple[int, str]], used: set) -> bool:
    """A finding is suppressed only when its span lies inside an occurrence of some `match`."""
    hit = False
    for i, match in allow:
        pos = text.find(match)
        while pos != -1:
            if pos <= span[0] and span[1] <= pos + len(match):
                used.add(i)
                hit = True
                break
            pos = text.find(match, pos + 1)
    return hit


_ALLOW_ENTRY = re.compile(r"meta\.secret_allow\[\d+\]")


def _strings(data: Any):
    """Yield (where, string) for every string value, skipping keys, `$schema` and secret_allow `match` values.

    Iterative on purpose: no recursion limit and no depth cap that a deep map could hide behind.
    """
    stack: list[tuple[Any, str]] = [(data, "")]
    while stack:
        value, where = stack.pop()
        if isinstance(value, str):
            yield where, value
        elif isinstance(value, dict):
            for key, child in value.items():
                if not isinstance(key, str):
                    continue
                if where == "" and key == "$schema":
                    continue
                if key == "match" and _ALLOW_ENTRY.fullmatch(where):
                    continue  # the allowed value itself; its `why` is scanned like any text
                stack.append((child, _join(where, _seg(key))))
        elif isinstance(value, list):
            for i, child in enumerate(value):
                label = _ident(child, i) if where in ("nodes", "flows") else str(i)
                stack.append((child, f"{where}[{label}]"))


def find_secrets(data: Any) -> list[Problem]:
    """Secret-looking strings in the map, plus problems with `meta.secret_allow` itself."""
    allow: list[tuple[int, str]] = []  # (index, match) of usable entries
    problems: list[Problem] = []
    raw_allow = None
    if isinstance(data, dict) and isinstance(data.get("meta"), dict):
        raw_allow = data["meta"].get("secret_allow")
    if isinstance(raw_allow, list):
        for i, entry in enumerate(raw_allow):
            if not isinstance(entry, dict):
                continue
            match = entry.get("match")
            if not isinstance(match, str) or len(match) < SECRET_ALLOW_MIN_MATCH:
                continue  # shape problem, reported by the structure rules
            allow.append((i, match))
            why = entry.get("why")
            if "why" not in entry or (isinstance(why, str) and not why.strip()):
                problems.append(
                    _problem("secret-allow-no-why", f"meta.secret_allow[{i}].why", "secret_allow entry needs a 'why'")
                )
    used: set[int] = set()
    for where, text in _strings(data):
        for rule, start, end in scan_string(text):
            if _suppressed(text, (start, end), allow, used):
                continue
            problems.append(
                _problem("secret-suspect", where or "$", f"possible secret ({rule}): {_hint(text[start:end])}")
            )
    for i, match in allow:
        if i not in used:
            problems.append(
                _problem("secret-allow-unused", f"meta.secret_allow[{i}]", "secret_allow entry suppresses no finding")
            )
    problems.sort(key=lambda p: (p.where, p.code, p.message))
    return problems
