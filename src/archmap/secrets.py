"""Detect secret-looking strings in the map. Only string values are scanned."""

from __future__ import annotations

import re
from typing import Any, Iterator

from .problems import Problem

_CONN = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s/:@]+:[^\s/@]+@")
_ASSIGN = re.compile(r"\b(?:password|passwd|secret|token|api[_-]?key)\s*[=:]\s*\S{6,}", re.IGNORECASE)
_HEX = re.compile(r"[0-9a-fA-F]{32,}")
_B64 = re.compile(r"[A-Za-z0-9+=_-]{40,}")
_PREFIXES = re.compile(
    r"(?<![A-Za-z0-9_])(?:"
    r"sk-[A-Za-z0-9_-]{20,}"
    r"|ghp_[A-Za-z0-9]{30,}"
    r"|github_pat_[A-Za-z0-9_]{30,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"
    r"|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
    r")"
)
_STRIP = "'\"()[]{},;"


def _hint(text: str) -> str:
    """At most the first 4 characters of a suspect value, never the whole of it."""
    return text[:4] + "…"


def scan_string(text: str) -> list[tuple[str, str]]:
    """Sub-rule findings for one string, as (rule, matched text) pairs, one per rule."""
    found: dict[str, str] = {}
    m = _CONN.search(text)
    if m:
        found["connection-string"] = m.group()
    m = _ASSIGN.search(text)
    if m:
        found["assignment"] = m.group()
    for raw in text.split():
        token = raw.strip(_STRIP)
        if not token:
            continue
        if _HEX.fullmatch(token) and len(token) not in (40, 64):
            found.setdefault("hex-token", token)
        if (
            _B64.fullmatch(token)
            and any(c.isupper() for c in token)
            and any(c.islower() for c in token)
            and any(c.isdigit() for c in token)
        ):
            found.setdefault("base64-token", token)
        m = _PREFIXES.search(token)
        if m:
            found.setdefault("key-prefix", m.group())
    return list(found.items())


def _walk(value: Any, where: str, depth: int = 0) -> Iterator[tuple[str, str]]:
    """Yield (where, string) for every string value, skipping keys, `$schema` and secret_allow."""
    from .guard import _ident, _join, _seg  # lazy: guard imports this module

    if depth > 64:  # deeper than any real map; keeps the walk away from the recursion limit
        return
    if isinstance(value, str):
        yield where, value
    elif isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                continue
            if where == "" and key == "$schema":
                continue
            if where == "meta" and key == "secret_allow":
                continue
            yield from _walk(child, _join(where, _seg(key)), depth + 1)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            label = _ident(child, i) if where in ("nodes", "flows") else str(i)
            yield from _walk(child, f"{where}[{label}]", depth + 1)


def find_secrets(data: Any) -> list[Problem]:
    """Secret-looking strings in the map, plus problems with `meta.secret_allow` itself."""
    from .guard import _problem

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
            if not isinstance(match, str) or match == "":
                continue  # shape problem, reported by the structure rules
            allow.append((i, match))
            why = entry.get("why")
            if "why" not in entry or (isinstance(why, str) and not why.strip()):
                problems.append(
                    _problem("secret-allow-no-why", f"meta.secret_allow[{i}].why", "secret_allow entry needs a 'why'")
                )
    used: set[int] = set()
    for where, text in _walk(data, ""):
        findings = scan_string(text)
        if not findings:
            continue
        hit = [i for i, match in allow if match in text]
        used.update(hit)
        if hit:
            continue
        for rule, matched in findings:
            problems.append(
                _problem("secret-suspect", where or "$", f"possible secret ({rule}): {_hint(matched)}")
            )
    for i, match in allow:
        if i not in used:
            problems.append(
                _problem("secret-allow-unused", f"meta.secret_allow[{i}]", "secret_allow entry suppresses no finding")
            )
    return problems
