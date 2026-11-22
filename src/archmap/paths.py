"""Path, glob and file utilities. Matching is case-sensitive and uses `/` only."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal, Optional

SKIP_DIRS = frozenset({".git", "__pycache__", "node_modules"})

_DRIVE_RE = re.compile(r"^[A-Za-z]:")
MAX_SEGMENTS = 128


def too_broad(entry: str) -> bool:
    """A `files` entry that would cover the whole tree: `*`, `**`, or one starting with `**`."""
    return entry in ("*", "**") or entry.split("/", 1)[0] == "**"


def validate_rel_path(p: str) -> Optional[str]:
    """Return an error message for a bad relative path or glob, or None if it is fine."""
    if not isinstance(p, str) or p == "":
        return "path is empty"
    if "\\" in p:
        return "path must use '/' as separator, not a backslash"
    if p.startswith("/"):
        return "path must be relative, not start with '/'"
    if _DRIVE_RE.match(p):
        return "path must be relative, not start with a drive letter"
    segments = p.split("/")
    if segments[-1] == "":  # trailing '/' marks a directory
        segments = segments[:-1]
    if len(segments) > MAX_SEGMENTS:
        return f"path has more than {MAX_SEGMENTS} segments"
    for seg in segments:
        if seg == "":
            return "path has an empty segment ('//')"
        if seg == "..":
            return "path must not contain '..'"
        if "**" in seg and seg != "**":
            return "'**' must be a whole path segment"
    return None


def exists_exact(root: Path, rel: str) -> Optional[Literal["file", "dir"]]:
    """Existence check with exact-case names, on any OS. A trailing '/' is allowed."""
    segments = [s for s in rel.split("/") if s != ""]
    if not segments:
        return None
    current = Path(root)
    for i, seg in enumerate(segments):
        last = i == len(segments) - 1
        try:
            with os.scandir(current) as it:
                found = None
                for entry in it:
                    if entry.name == seg:
                        found = entry
                        break
                if found is None:
                    return None
                is_dir = found.is_dir()
        except OSError:
            return None
        if last:
            return "dir" if is_dir else "file"
        if not is_dir:
            return None
        current = current / seg
    return None


def is_glob(entry: str) -> bool:
    return "*" in entry or "?" in entry


def _segment_match(pat: str, name: str) -> bool:
    """`*` matches any run of characters, `?` exactly one; everything else is literal."""
    p = n = 0
    star = -1
    mark = 0
    while n < len(name):
        if p < len(pat) and pat[p] == "*":
            star = p
            mark = n
            p += 1
        elif p < len(pat) and (pat[p] == "?" or pat[p] == name[n]):
            p += 1
            n += 1
        elif star != -1:
            p = star + 1
            mark += 1
            n = mark
        else:
            return False
    while p < len(pat) and pat[p] == "*":
        p += 1
    return p == len(pat)


def glob_match(pattern: str, rel: str) -> bool:
    """Segment-wise match with `**` for any number of segments. Iterative: it cannot recurse."""
    pat = pattern.split("/")
    parts = rel.split("/")
    n = len(parts)
    reach = {0}  # path positions reachable after the pattern segments consumed so far
    for seg in pat:
        if not reach:
            return False
        if seg == "**":
            reach = set(range(min(reach), n + 1))
        else:
            reach = {j + 1 for j in reach if j < n and _segment_match(seg, parts[j])}
    return n in reach


def expand_glob(root: Path, pattern: str) -> list[str]:
    """Files under `root` matching `pattern`, as sorted POSIX relative paths."""
    root = Path(root)
    segments = pattern.split("/")
    prefix: list[str] = []
    for seg in segments:
        if is_glob(seg):
            break
        prefix.append(seg)
    if len(prefix) == len(segments):  # no glob at all
        return [pattern] if exists_exact(root, pattern) == "file" else []
    if prefix and exists_exact(root, "/".join(prefix)) != "dir":
        return []
    start_rel = "/".join(prefix)
    start = root.joinpath(*prefix) if prefix else root
    found: list[str] = []
    stack = [(start, start_rel)]
    while stack:
        directory, rel_dir = stack.pop()
        try:
            with os.scandir(directory) as it:
                entries = list(it)
        except OSError:
            continue
        for entry in entries:
            rel = f"{rel_dir}/{entry.name}" if rel_dir else entry.name
            try:
                if entry.is_dir(follow_symlinks=False):
                    if entry.name not in SKIP_DIRS:
                        stack.append((Path(entry.path), rel))
                elif entry.is_file() and glob_match(pattern, rel):
                    found.append(rel)
            except OSError:
                continue
    return sorted(found)


def covers(entry: str, rel: str, root: Optional[Path] = None) -> bool:
    """Does a `files` entry cover the path `rel`? Pure string logic, except that a
    literal entry without a trailing '/' is a directory prefix when `root` says so."""
    if is_glob(entry):
        return glob_match(entry, rel)
    if entry.endswith("/"):
        return rel.startswith(entry) and rel != entry
    if rel == entry:
        return True
    if root is not None and rel.startswith(entry + "/"):
        return exists_exact(root, entry) == "dir"
    return False


def _read_text(path: Path) -> tuple[Optional[str], Optional[str]]:
    """(text, None), or (None, reason) when the file is not text."""
    with open(path, "rb") as fh:
        raw = fh.read()
    if b"\x00" in raw[:8192]:
        return None, "binary (NUL byte)"
    try:
        return raw.decode("utf-8-sig"), None
    except UnicodeDecodeError:
        return None, "not valid UTF-8"


def binary_reason(path: Path) -> Optional[str]:
    """Why `count_lines` gives None for this file: "binary (NUL byte)" or "not valid UTF-8"."""
    return _read_text(path)[1]


def count_lines(path: Path) -> Optional[int]:
    """Number of text lines, or None for a binary file (NUL in the first 8 KiB, or not UTF-8)."""
    text, _ = _read_text(path)
    if text is None:
        return None
    if text == "":
        return 0
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.count("\n") + (0 if text.endswith("\n") else 1)
