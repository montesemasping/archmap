"""Detect secret-looking strings in the map. Only string values are scanned."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from .problems import Problem
from .schema import SECRET_ALLOW_MIN_MATCH
from .where import _ident, _join, _problem, _seg

# (a) scheme://user:pass@ . The user may be empty (redis://:pw@host). A password that
# itself contains '/' is not caught: the pattern cannot tell it from the start of a path.
_CONN = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s/:@]*:[^\s/@]+@")
# (b) keyword, optional identifier tail (SECRET_KEY, AWS_SECRET_ACCESS_KEY), then = or : and a value.
# No leading \b: it would not match after '_' (DB_PASSWORD).
_ASSIGN = re.compile(
    r"(?:password|passwd|secret|token|api[_-]?key)[A-Za-z0-9_]*\s*[=:]\s*(\S+)", re.IGNORECASE
)
_PLACEHOLDER = re.compile(
    r"\$\{.*\}|<.*>|:[A-Za-z_]\w*|\$[A-Za-z_]\w*|\{\{.*\}\}|%\(.*\)s|\*+|[xX]+"
)
_HEX = re.compile(r"[0-9a-fA-F]{32,}")
_B64 = re.compile(r"[A-Za-z0-9+=_-]{40,}")
_B64_MIN_ENTROPY = 4.4  # bits per character; identifiers and paths sit well below
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
_STRIP = "'\"()[]{},;:.!?`<>*"
_VALUE_QUOTES = "'\"`"
_PIECE = re.compile(r"[^\s]+")
_SUBPIECE = re.compile(r"[^?&=]+")


def _hint(text: str) -> str:
    """At most the first 4 characters of a suspect value, never the whole of it."""
    return text[:4] + "…"


def entropy(text: str) -> float:
    counts = Counter(text)
    n = len(text)
    return -sum(c / n * math.log2(c / n) for c in counts.values())


def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start] in _STRIP:
        start += 1
    while end > start and text[end - 1] in _STRIP:
        end -= 1
    return start, end


def _tokens(text: str):
    """Whitespace pieces, then those pieces split on ? & = (query values), punctuation-trimmed."""
    seen = set()
    for piece in _PIECE.finditer(text):
        s, e = _trim(text, piece.start(), piece.end())
        if s < e and (s, e) not in seen:
            seen.add((s, e))
            yield s, e
        for sub in _SUBPIECE.finditer(text, piece.start(), piece.end()):
            s2, e2 = _trim(text, sub.start(), sub.end())
            if s2 < e2 and (s2, e2) not in seen:
                seen.add((s2, e2))
                yield s2, e2


def _assignment_fires(value: str) -> bool:
    value = value.strip(_VALUE_QUOTES + ",;")
    if len(value) < 6 or _PLACEHOLDER.fullmatch(value):
        return False
    return len(value) >= 12 or any(not c.isalpha() for c in value)


def scan_string(text: str) -> list[tuple[str, int, int]]:
    """Findings in one string as (rule, start, end) spans."""
    found: set[tuple[str, int, int]] = set()
    for m in _CONN.finditer(text):
        found.add(("connection-string", m.start(), m.end()))
    for m in _ASSIGN.finditer(text):
        if _assignment_fires(m.group(1)):
            found.add(("assignment", m.start(), m.end()))
    for s, e in _tokens(text):
        token = text[s:e]
        if _HEX.fullmatch(token) and len(token) not in (40, 64):
            found.add(("hex-token", s, e))
        if (
            _B64.fullmatch(token)
            and any(c.isupper() for c in token)
            and any(c.islower() for c in token)
            and any(c.isdigit() for c in token)
            and entropy(token) >= _B64_MIN_ENTROPY
        ):
            found.add(("base64-token", s, e))
        for m in _PREFIXES.finditer(token):
            found.add(("key-prefix", s + m.start(), s + m.end()))
    return sorted(found, key=lambda f: (f[1], f[2], f[0]))


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


def _strings(data: Any):
    """Yield (where, string) for every string value, skipping keys, `$schema` and secret_allow.

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
                if where == "meta" and key == "secret_allow":
                    continue
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
