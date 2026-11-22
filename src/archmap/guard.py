"""Structure and path rules for an architecture map.

`check_map` never raises: any JSON value yields a list of problems.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from . import schema
from .paths import count_lines, covers, exists_exact, expand_glob, is_glob, validate_rel_path
from .problems import Problem
from .secrets import find_secrets
from .where import GUARD_CODES, _SAFE_ID, _ident, _join, _problem, _seg  # noqa: F401


def _blank(value: Any) -> bool:
    return not isinstance(value, str) or not value.strip()


_TYPES = {"str": str, "list": list, "dict": dict}
_TYPE_NAMES = {"str": "a string", "list": "a list", "dict": "an object"}


class _Guard:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.problems: list[Problem] = []

    def add(self, code: str, where: str, message: str) -> None:
        self.problems.append(_problem(code, where, message))

    # ---- generic object checks -------------------------------------------------

    def fields(self, obj: Any, where: str, known: dict, required: tuple) -> bool:
        """Check that `obj` is an object with known, well-typed fields. False if not an object."""
        if not isinstance(obj, dict):
            self.add("field-invalid", where, "expected an object")
            return False
        for key in obj:
            if key not in known:
                self.add("field-unknown", _join(where, _seg(key)), f"unknown field {key!r}")
        for key, kind in known.items():
            if key not in obj:
                continue
            value = obj[key]
            expected = _TYPES.get(kind)
            if expected is not None and not isinstance(value, expected):
                self.add("field-invalid", _join(where, key), f"expected {_TYPE_NAMES[kind]}")
        for key in required:
            kind = known[key]
            if key not in obj:
                self.add("field-missing", _join(where, key), f"missing required field '{key}'")
            elif kind == "str" and isinstance(obj[key], str) and not obj[key].strip():
                self.add("field-missing", _join(where, key), f"required field '{key}' is empty")
        return True

    def str_items(self, items: Any, where: str) -> None:
        if isinstance(items, list):
            for i, item in enumerate(items):
                if not isinstance(item, str):
                    self.add("field-invalid", f"{where}[{i}]", "expected a string")

    # ---- paths -----------------------------------------------------------------

    def check_path(self, value: Any, where: str, allow_glob: bool) -> Optional[str]:
        """Validate a path entry; return "file"/"dir" for an existing literal path, else None."""
        if not isinstance(value, str):
            return None  # the type error is reported by the field check
        error = validate_rel_path(value)
        if error is not None:
            self.add("path-invalid", where, f"{value!r}: {error}")
            return None
        if is_glob(value):
            if not allow_glob:
                self.add("path-invalid", where, f"{value!r}: globs are only allowed in nodes[].files")
            elif not expand_glob(self.root, value):
                self.add("glob-empty", where, f"glob {value!r} matches no file")
            return None
        kind = exists_exact(self.root, value)
        if kind is None:
            self.add("path-missing", where, f"{value!r} does not exist (names are case-sensitive)")
        elif kind == "file" and value.endswith("/"):
            self.add("path-missing", where, f"{value!r} is a file, not a directory")
            return None
        return kind

    def check_line(self, step: dict, where: str, kind: Optional[str]) -> None:
        if "line" not in step:
            return
        line = step["line"]
        here = _join(where, "line")
        if isinstance(line, bool) or not isinstance(line, int):
            self.add("field-invalid", here, "expected an integer")
            return
        if line < 1:
            self.add("line-invalid", here, f"line must be at least 1, got {line}")
            return
        path = step.get("path")
        if not isinstance(path, str) or path == "":
            self.add("line-invalid", here, "line is given without a path")
            return
        if kind is None:
            return  # the path itself is already reported as invalid or missing
        if kind == "dir":
            self.add("line-invalid", here, f"line is given but {path!r} is a directory")
            return
        try:
            total = count_lines(self.root.joinpath(*path.split("/")))
        except (OSError, ValueError) as exc:
            self.add("line-invalid", here, f"cannot read {path!r}: {exc}")
            return
        if total is None:
            self.add("line-invalid", here, f"{path!r} is a binary file, a line number makes no sense")
        elif line > total:
            self.add("line-invalid", here, f"line {line} is beyond the end of {path!r} ({total} lines)")

    def check_optional_path_items(self, items: Any, where: str, fields: dict, required: tuple) -> None:
        """entrypoints / reading_order: objects with an optional literal path."""
        if not isinstance(items, list):
            return
        for i, item in enumerate(items):
            here = f"{where}[{i}]"
            if self.fields(item, here, fields, required) and "path" in item:
                self.check_path(item["path"], f"{here}.path", allow_glob=False)

    # ---- sections of the map ---------------------------------------------------

    def meta(self, meta: Any) -> Optional[set]:
        """Check meta; return the set of declared layer ids (None if layers is unusable)."""
        if not self.fields(meta, "meta", schema.META_FIELDS, schema.META_REQUIRED):
            return None
        url = meta.get("source_url")
        if isinstance(url, str) and not url.startswith(("http://", "https://")):
            self.add("field-invalid", "meta.source_url", "must start with http:// or https://")
        layer_ids: Optional[set] = None
        layers = meta.get("layers")
        if isinstance(layers, list):
            layer_ids = set()
            first_layer: dict = {}
            for i, layer in enumerate(layers):
                here = f"meta.layers[{i}]"
                if self.fields(layer, here, schema.LAYER_FIELDS, schema.LAYER_REQUIRED):
                    lid = layer.get("id")
                    if not _blank(lid):
                        if lid in first_layer:
                            self.add("id-duplicate", f"{here}.id", f"duplicate layer id {lid!r} (first at meta.layers[{first_layer[lid]}])")
                        else:
                            first_layer[lid] = i
                        layer_ids.add(lid)
        self.check_optional_path_items(
            meta.get("entrypoints"), "meta.entrypoints", schema.ENTRYPOINT_FIELDS, schema.ENTRYPOINT_REQUIRED
        )
        coverage = meta.get("coverage")
        if isinstance(coverage, dict) and self.fields(
            coverage, "meta.coverage", schema.COVERAGE_FIELDS, schema.COVERAGE_REQUIRED
        ):
            self.str_items(coverage.get("core"), "meta.coverage.core")
            ignored = coverage.get("ignored")
            if isinstance(ignored, list):
                for i, item in enumerate(ignored):
                    self.fields(item, f"meta.coverage.ignored[{i}]", schema.IGNORED_FIELDS, schema.IGNORED_REQUIRED)
        allow = meta.get("secret_allow")
        if isinstance(allow, list):
            for i, item in enumerate(allow):
                if self.fields(item, f"meta.secret_allow[{i}]", schema.SECRET_ALLOW_FIELDS, schema.SECRET_ALLOW_REQUIRED):
                    match = item.get("match")
                    if isinstance(match, str) and 0 < len(match.strip()) and len(match) < schema.SECRET_ALLOW_MIN_MATCH:
                        self.add(
                            "field-invalid", f"meta.secret_allow[{i}].match",
                            f"match must be at least {schema.SECRET_ALLOW_MIN_MATCH} characters",
                        )
        return layer_ids

    def nodes(self, nodes: Any, layer_ids: Optional[set]) -> Optional[set]:
        """Check nodes; return the set of node ids (None if nodes is not a list)."""
        if not isinstance(nodes, list):
            return None
        ids: set = set()
        seen: dict = {}
        for i, node in enumerate(nodes):
            where = f"nodes[{_ident(node, i)}]"
            if not isinstance(node, dict):
                self.add("field-invalid", f"nodes[{i}]", "expected an object")
                continue
            self.fields(node, where, schema.NODE_FIELDS, schema.NODE_REQUIRED)
            nid = node.get("id")
            if isinstance(nid, str) and nid.strip():
                if nid in seen:
                    self.add("id-duplicate", f"{where}.id", f"duplicate node id {nid!r} (first at nodes[{seen[nid]}])")
                else:
                    seen[nid] = i
                ids.add(nid)
            layer = node.get("layer")
            if layer_ids is not None and isinstance(layer, str) and layer.strip() and layer not in layer_ids:
                self.add("layer-undeclared", f"{where}.layer", f"layer {layer!r} is not declared in meta.layers")
            files = node.get("files")
            if isinstance(files, list):
                for j, entry in enumerate(files):
                    here = f"{where}.files[{j}]"
                    if isinstance(entry, str):
                        self.check_path(entry, here, allow_glob=True)
                    else:
                        self.add("field-invalid", here, "expected a string")
            for key in ("details", "api"):
                self.str_items(node.get(key), f"{where}.{key}")
        return ids

    def edges(self, edges: Any, node_ids: Optional[set]) -> set:
        """Check edges; return the set of node ids that appear in some edge."""
        linked: set = set()
        if not isinstance(edges, list):
            return linked
        for i, edge in enumerate(edges):
            where = f"edges[{i}]"
            if not self.fields(edge, where, schema.EDGE_FIELDS, schema.EDGE_REQUIRED):
                continue
            ends = {}
            for key in ("from", "to"):
                value = edge.get(key)
                if isinstance(value, str) and value.strip():
                    ends[key] = value
                    linked.add(value)
                    if node_ids is not None and value not in node_ids:
                        self.add("edge-dangling", f"{where}.{key}", f"unknown node {value!r}")
            if len(ends) == 2 and ends["from"] == ends["to"]:
                self.add("edge-self", where, f"edge connects node {ends['from']!r} to itself")
        return linked

    def flows(self, flows: Any, node_ids: Optional[set]) -> None:
        if not isinstance(flows, list):
            return
        seen: dict = {}
        for i, flow in enumerate(flows):
            where = f"flows[{_ident(flow, i)}]"
            if not isinstance(flow, dict):
                self.add("field-invalid", f"flows[{i}]", "expected an object")
                continue
            self.fields(flow, where, schema.FLOW_FIELDS, schema.FLOW_REQUIRED)
            fid = flow.get("id")
            if isinstance(fid, str) and fid.strip():
                if fid in seen:
                    self.add("id-duplicate", f"{where}.id", f"duplicate flow id {fid!r} (first at flows[{seen[fid]}])")
                else:
                    seen[fid] = i
            self.str_items(flow.get("tags"), f"{where}.tags")
            steps = flow.get("steps")
            if not isinstance(steps, list):
                continue
            if len(steps) < 2:
                self.add("flow-too-short", f"{where}.steps", f"a flow needs at least 2 steps, found {len(steps)}")
            for j, step in enumerate(steps):
                here = f"{where}.steps[{j}]"
                if not self.fields(step, here, schema.STEP_FIELDS, schema.STEP_REQUIRED):
                    continue
                target = step.get("node")
                if node_ids is not None and isinstance(target, str) and target.strip() and target not in node_ids:
                    self.add("step-node-missing", f"{here}.node", f"unknown node {target!r}")
                kind = None
                if "path" in step:
                    kind = self.check_path(step["path"], f"{here}.path", allow_glob=False)
                self.check_line(step, here, kind)

    def notes(self, items: Any, where: str) -> None:
        """gotchas / unknowns: strings or {text, path?}."""
        if not isinstance(items, list):
            return
        for i, item in enumerate(items):
            if isinstance(item, str):
                continue
            here = f"{where}[{i}]"
            if self.fields(item, here, schema.NOTE_FIELDS, schema.NOTE_REQUIRED) and "path" in item:
                self.check_path(item["path"], f"{here}.path", allow_glob=False)

    def sections(self, sections: Any) -> None:
        if not isinstance(sections, dict):
            return
        for name, section in sections.items():
            where = f"sections.{_seg(name)}"
            if self.fields(section, where, schema.SECTION_FIELDS, schema.SECTION_REQUIRED):
                if "body" not in section and "items" not in section:
                    self.add("field-missing", f"{where}.body", "a section needs 'body' or 'items'")
                elif "body" in section and "items" in section:
                    self.add("field-invalid", f"{where}.items", "give either 'body' or 'items', not both")

    # ---- core coverage ---------------------------------------------------------

    def core_files(self, core: list) -> set:
        """Files under the core entries; reports empty and invalid entries."""
        files: set = set()
        for i, entry in enumerate(core):
            where = f"meta.coverage.core[{i}]"
            error = validate_rel_path(entry)
            if error is not None:
                self.add("path-invalid", where, f"{entry!r}: {error}")
                continue
            if is_glob(entry):
                found = expand_glob(self.root, entry)
            elif exists_exact(self.root, entry) == "dir":
                found = expand_glob(self.root, entry.rstrip("/") + "/**")
            elif exists_exact(self.root, entry) == "file" and not entry.endswith("/"):
                found = [entry]
            else:
                found = []
            if not found:
                self.add("coverage-core-glob-empty", where, f"core entry {entry!r} matches no file")
            files.update(found)
        return files

    def coverage(self, data: dict) -> None:
        meta = data.get("meta")
        cov = meta.get("coverage") if isinstance(meta, dict) else None
        if not isinstance(cov, dict) or not isinstance(cov.get("core"), list):
            return  # malformed: already reported by the structure rules
        core = [e for e in cov["core"] if isinstance(e, str)]
        if len(core) != len(cov["core"]):
            return
        if not core:
            self.add("coverage-core-empty", "meta.coverage.core", "the core must list at least one entry")
            return
        files = self.core_files(core)
        ignored = []
        raw = cov.get("ignored")
        for i, item in enumerate(raw if isinstance(raw, list) else []):
            if not isinstance(item, dict) or not isinstance(item.get("glob"), str) or not item["glob"].strip():
                continue
            where = f"meta.coverage.ignored[{i}]"
            why = item.get("why")
            if "why" not in item or (isinstance(why, str) and not why.strip()):
                self.add("coverage-ignore-no-why", f"{where}.why", "an ignored entry needs a 'why'")
            error = validate_rel_path(item["glob"])
            if error is not None:
                self.add("path-invalid", f"{where}.glob", f"{item['glob']!r}: {error}")
                continue
            ignored.append((where, item["glob"]))
        skipped: set = set()
        for where, glob in ignored:
            hits = {f for f in files if covers(glob, f, self.root)}
            if not hits:
                self.add("coverage-ignore-unused", where, f"ignored entry {glob!r} matches no core file")
            skipped |= hits
        entries = []
        nodes = data.get("nodes")
        for node in nodes if isinstance(nodes, list) else []:
            listed = node.get("files") if isinstance(node, dict) else None
            for entry in listed if isinstance(listed, list) else []:
                if isinstance(entry, str) and validate_rel_path(entry) is None:
                    entries.append(entry)
        for rel in sorted(files - skipped):
            if not any(covers(entry, rel, self.root) for entry in entries):
                self.add("coverage-uncovered", "meta.coverage", f"core file {rel!r} is not covered by any node's files")

    # ---- entry ----------------------------------------------------------------

    def run(self, data: dict) -> list[Problem]:
        for key in schema.TOP_REQUIRED:
            if key not in data:
                self.add("section-missing", "$", f"missing required section '{key}'")
        for key in data:
            if key not in schema.TOP_FIELDS:
                self.add("field-unknown", _seg(key), f"unknown top-level field {key!r}")
        for key, kind in schema.TOP_FIELDS.items():
            if key in data and key != "$schema" and not isinstance(data[key], _TYPES[kind]):
                self.add("field-invalid", key, f"expected {_TYPE_NAMES[kind]}")
        layer_ids = self.meta(data["meta"]) if isinstance(data.get("meta"), dict) else None
        node_ids = self.nodes(data.get("nodes"), layer_ids)
        linked = self.edges(data.get("edges"), node_ids)
        if node_ids is not None and isinstance(data.get("edges"), list):
            reported: set = set()
            for i, node in enumerate(data["nodes"]):
                nid = node.get("id") if isinstance(node, dict) else None
                if isinstance(nid, str) and nid.strip() and nid not in linked and nid not in reported:
                    reported.add(nid)
                    self.add("node-orphan", f"nodes[{_ident(node, i)}]", f"node {nid!r} has no edges")
        self.flows(data.get("flows"), node_ids)
        self.check_optional_path_items(
            data.get("reading_order"), "reading_order", schema.READING_FIELDS, schema.READING_REQUIRED
        )
        self.notes(data.get("gotchas"), "gotchas")
        self.notes(data.get("unknowns"), "unknowns")
        self.sections(data.get("sections"))
        self.coverage(data)
        self.problems.extend(find_secrets(data))
        self.problems.sort(key=lambda p: (p.where, p.code))
        return self.problems


def check_map(data: Any, root: "str | os.PathLike") -> list[Problem]:
    """All problems found in the map `data`, sorted by (where, code). Never raises."""
    if not isinstance(data, dict) or "$schema" not in data:
        return [_problem("schema-missing", "$", "map must be a JSON object with a '$schema' field")]
    if data["$schema"] != schema.SCHEMA_ID:
        return [
            _problem(
                "schema-unknown",
                "$schema",
                f"unsupported schema {data['$schema']!r}, expected {schema.SCHEMA_ID!r}",
            )
        ]
    return _Guard(Path(root)).run(data)
