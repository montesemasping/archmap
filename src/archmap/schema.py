"""Known and required fields of the `archmap/1` schema.

Field types: "str" (a string), "list", "dict", "any" (free-form JSON). Required strings
that are empty or whitespace-only count as missing.
"""

from __future__ import annotations

SCHEMA_ID = "archmap/1"

TOP_FIELDS = {
    "$schema": "str",
    "meta": "dict",
    "nodes": "list",
    "edges": "list",
    "flows": "list",
    "reading_order": "list",
    "gotchas": "list",
    "unknowns": "list",
    "sections": "dict",
}
TOP_REQUIRED = ("$schema", "meta", "nodes", "edges", "flows")

META_FIELDS = {
    "project": "str",
    "title": "str",
    "updated_at": "str",
    "purpose": "str",
    "stack": "any",
    "layers": "list",
    "entrypoints": "list",
    "conventions": "any",
    "maintenance": "any",
    "coverage": "dict",
    "source_url": "str",
    "secret_allow": "list",
}
META_REQUIRED = ("project", "title", "layers", "coverage")

COVERAGE_FIELDS = {"core": "list", "ignored": "list"}
COVERAGE_REQUIRED = ("core",)

IGNORED_FIELDS = {"glob": "str", "why": "str"}
IGNORED_REQUIRED = ("glob",)

SECRET_ALLOW_FIELDS = {"match": "str", "why": "str"}
SECRET_ALLOW_REQUIRED = ("match",)

LAYER_FIELDS = {"id": "str", "title": "str", "hint": "str"}
LAYER_REQUIRED = ("id",)

ENTRYPOINT_FIELDS = {"path": "str", "what": "str"}
ENTRYPOINT_REQUIRED = ("what",)

NODE_FIELDS = {
    "id": "str",
    "label": "str",
    "layer": "str",
    "kind": "str",
    "files": "list",
    "summary": "str",
    "details": "list",
    "api": "list",
    "status": "str",
    "tech": "any",
}
NODE_REQUIRED = ("id", "label", "layer", "summary")

EDGE_FIELDS = {"from": "str", "to": "str", "label": "str", "kind": "str"}
EDGE_REQUIRED = ("from", "to")

FLOW_FIELDS = {"id": "str", "title": "str", "summary": "str", "tags": "list", "steps": "list"}
FLOW_REQUIRED = ("id", "title", "steps")

# `line` is checked separately: it is an int, not a string.
STEP_FIELDS = {"node": "str", "note": "str", "path": "str", "line": "line", "symbol": "str"}
STEP_REQUIRED = ("node", "note")

READING_FIELDS = {"path": "str", "why": "str"}
READING_REQUIRED = ("why",)

NOTE_FIELDS = {"text": "str", "path": "str"}  # gotchas / unknowns object form
NOTE_REQUIRED = ("text",)

SECTION_FIELDS = {"title": "str", "body": "any", "items": "list"}
SECTION_REQUIRED = ("title",)
