"""Secret-pattern primitives: scan one string. A leaf module, shared by `secrets` and `where`."""

from __future__ import annotations

import math
import re
from collections import Counter

# (a) scheme://user:pass@ . The user may be empty (redis://:pw@host). A password that
# itself contains '/' is not caught: the pattern cannot tell it from the start of a path.
_CONN = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s/:@]*:[^\s/@]+@")
# (b) keyword, optional identifier tail (SECRET_KEY, AWS_SECRET_ACCESS_KEY), then = or : and a value.
# No leading \b: it would not match after '_' (DB_PASSWORD). `pass` is a whole word only, so
# DB_PASS=... fires while bypass, passport and compass do not.
_ASSIGN = re.compile(
    r"(?:password|passwd|secret|token|api[_-]?key|(?<![A-Za-z0-9])pass(?![A-Za-z0-9]))"
    r"[A-Za-z0-9_]*\s*[=:]\s*(\S+)",
    re.IGNORECASE,
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
    r"|gh[pousr]_[A-Za-z0-9]{30,}"
    r"|(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}"
    r"|AIza[0-9A-Za-z_-]{35}"
    r"|glpat-[A-Za-z0-9_-]{20,}"
    r"|ASIA[0-9A-Z]{16}(?![A-Za-z0-9])"
    r"|npm_[A-Za-z0-9]{36}"
    r"|github_pat_[A-Za-z0-9_]{30,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"
    r"|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
    r")"
)
# Spans whitespace, so it cannot be matched token by token.
_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
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
    for m in _PRIVATE_KEY.finditer(text):
        found.add(("key-prefix", m.start(), m.end()))
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
