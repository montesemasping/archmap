"""Render the map into one self-contained offline HTML page."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

from . import paths
from ._version import __version__
from .problems import Problem

PLACEHOLDER = "/*__ARCHMAP_DATA__*/"
_ESCAPES = {
    "<": "\\u003c",
    ">": "\\u003e",
    "&": "\\u0026",
    "\u2028": "\\u2028",
    "\u2029": "\\u2029",
}


def _template_text() -> str:
    try:
        from . import _bundled
    except ImportError:
        import importlib.resources

        resource = importlib.resources.files(__package__) / "template.html"
        return resource.read_text(encoding="utf-8")
    return _bundled.TEMPLATE


def source_link(template: str, path: str, line: int | None) -> str:
    """Fill `{path}` and `{line}` of a source URL template; other braces stay as they are."""
    marker = "{line}"
    if isinstance(line, int) and not isinstance(line, bool):
        template = template.replace(marker, str(line))
    elif marker in template:
        first = template.index(marker)
        cut = template.rfind("#", 0, first)
        if cut >= 0:
            template = template[:cut]
        else:
            template = template.replace(marker, "")
    return template.replace("{path}", quote(path, safe="/"))


def _usable(path: Any) -> bool:
    return isinstance(path, str) and paths.validate_rel_path(path) is None


def _dicts(value: Any) -> list[dict]:
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def _build_links(data: dict) -> dict[str, str]:
    meta = data.get("meta")
    template = meta.get("source_url") if isinstance(meta, dict) else None
    if not (isinstance(template, str) and template.startswith(("http://", "https://"))):
        return {}
    links: dict[str, str] = {}

    def add(path: Any, line: Any = None) -> None:
        if not _usable(path):
            return
        links[path] = source_link(template, path, None)
        if isinstance(line, int) and not isinstance(line, bool) and line >= 1:
            links[f"{path}#{line}"] = source_link(template, path, line)

    for node in _dicts(data.get("nodes")):
        files = node.get("files")
        for entry in files if isinstance(files, list) else []:
            if _usable(entry) and not paths.is_glob(entry):
                add(entry)
    for key in ("entrypoints", "reading_order"):
        container = meta if key == "entrypoints" and isinstance(meta, dict) else data
        for item in _dicts(container.get(key)):
            add(item.get("path"))
    for key in ("gotchas", "unknowns"):
        for item in _dicts(data.get(key)):
            add(item.get("path"))
    for flow in _dicts(data.get("flows")):
        for step in _dicts(flow.get("steps")):
            add(step.get("path"), step.get("line"))
    return links


def render_html(data: dict, problems: list[Problem]) -> str:
    """Return the viewer page with the map, problems and source links embedded."""
    payload = {
        "map": data,
        "problems": [str(p) for p in problems],
        "version": __version__,
        "links": _build_links(data) if isinstance(data, dict) else {},
    }
    text = json.dumps(payload, ensure_ascii=False)
    for char, escaped in _ESCAPES.items():
        text = text.replace(char, escaped)
    return _template_text().replace(PLACEHOLDER, text, 1)
