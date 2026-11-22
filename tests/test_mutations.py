"""Every guard code has at least one mutation of the clean fixture that triggers it."""
import json
import shutil
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "bakery"
MAP_REL = "docs/architecture-map.json"

# The codes implemented so far. The next PR extends this with coverage-* and secret-*.
CODES = {
    "schema-missing", "schema-unknown", "section-missing", "field-missing", "field-invalid",
    "field-unknown", "id-duplicate", "layer-undeclared", "path-invalid", "path-missing",
    "glob-empty", "line-invalid", "edge-dangling", "edge-self", "node-orphan",
    "step-node-missing", "flow-too-short",
}


def _step(d):
    return d["flows"][0]["steps"][1]  # has path, line and symbol


def _set(path, value):
    def fn(d):
        cur = d
        for key in path[:-1]:
            cur = cur[key]
        cur[path[-1]] = value
    return fn


def _delete(path):
    def fn(d):
        cur = d
        for key in path[:-1]:
            cur = cur[key]
        del cur[path[-1]]
    return fn


def _step_update(**kw):
    return lambda d: _step(d).update(kw)


def _drop_step_path(d):
    del _step(d)["path"]


def _dup(section):
    def fn(d):
        d[section].append(json.loads(json.dumps(d[section][0])))
    return fn


def _add_orphan(d):
    d["nodes"].append({"id": "lonely", "label": "Lonely", "layer": "backend", "summary": "No edges."})


def _one_step(d):
    d["flows"][0]["steps"] = d["flows"][0]["steps"][:1]


# (name, mutate_map, expected_code); mutate_map(data) edits the parsed map in place.
MAP_MUTATIONS = [
    ("schema-field-absent", _delete(["$schema"]), "schema-missing"),
    ("schema-null", _set(["$schema"], None), "schema-unknown"),
    ("schema-wrong-version", _set(["$schema"], "archmap/2"), "schema-unknown"),
    ("section-nodes-missing", _delete(["nodes"]), "section-missing"),
    ("section-meta-missing", _delete(["meta"]), "section-missing"),
    ("section-edges-missing", _delete(["edges"]), "section-missing"),
    ("section-flows-missing", _delete(["flows"]), "section-missing"),
    ("field-missing-meta-title", _delete(["meta", "title"]), "field-missing"),
    ("field-missing-meta-coverage", _delete(["meta", "coverage"]), "field-missing"),
    ("field-missing-node-summary", _delete(["nodes", 0, "summary"]), "field-missing"),
    ("field-blank-node-label", _set(["nodes", 0, "label"], "   "), "field-missing"),
    ("field-missing-edge-to", _delete(["edges", 0, "to"]), "field-missing"),
    ("field-missing-flow-title", _delete(["flows", 0, "title"]), "field-missing"),
    ("field-missing-step-note", _delete(["flows", 0, "steps", 0, "note"]), "field-missing"),
    ("field-missing-layer-id", _delete(["meta", "layers", 0, "id"]), "field-missing"),
    ("field-missing-entrypoint-what", _delete(["meta", "entrypoints", 0, "what"]), "field-missing"),
    ("field-missing-reading-why", _delete(["reading_order", 0, "why"]), "field-missing"),
    ("field-missing-section-title", _delete(["sections", "roadmap", "title"]), "field-missing"),
    ("field-missing-section-body", _delete(["sections", "roadmap", "body"]), "field-missing"),
    ("field-missing-gotcha-text", _set(["gotchas", 1], {"path": "app/orders/api.py"}), "field-missing"),
    ("field-missing-coverage-core", _delete(["meta", "coverage", "core"]), "field-missing"),
    ("field-invalid-nodes-string", _set(["nodes"], "oops"), "field-invalid"),
    ("field-invalid-node-number", _set(["nodes", 0], 7), "field-invalid"),
    ("field-invalid-steps-object", _set(["flows", 0, "steps"], {"a": 1}), "field-invalid"),
    ("field-invalid-files-string", _set(["nodes", 0, "files"], "app/orders/api.py"), "field-invalid"),
    ("field-invalid-files-item", _set(["nodes", 0, "files", 0], 5), "field-invalid"),
    ("field-invalid-meta-list", _set(["meta"], []), "field-invalid"),
    ("field-invalid-source-url", _set(["meta", "source_url"], "ftp://x/{path}"), "field-invalid"),
    ("field-invalid-line-bool", _step_update(line=True), "field-invalid"),
    ("field-invalid-line-string", _step_update(line="3"), "field-invalid"),
    ("field-invalid-coverage-core-str", _set(["meta", "coverage", "core"], "app/**"), "field-invalid"),
    ("field-invalid-coverage-ignored-item", _set(["meta", "coverage", "ignored", 0], "x"), "field-invalid"),
    ("field-invalid-secret-allow-str", _set(["meta", "secret_allow"], "x"), "field-invalid"),
    ("field-invalid-secret-allow-why", _set(["meta", "secret_allow", 0, "why"], 4), "field-invalid"),
    ("field-invalid-section-items", _set(["sections", "how_to_read", "items"], "x"), "field-invalid"),
    ("field-invalid-sections-list", _set(["sections"], []), "field-invalid"),
    ("field-unknown-top", _set(["extra"], 1), "field-unknown"),
    ("field-unknown-meta", _set(["meta", "extra"], 1), "field-unknown"),
    ("field-unknown-node", _set(["nodes", 0, "extra"], 1), "field-unknown"),
    ("field-unknown-edge", _set(["edges", 0, "extra"], 1), "field-unknown"),
    ("field-unknown-flow", _set(["flows", 0, "extra"], 1), "field-unknown"),
    ("field-unknown-step", _set(["flows", 0, "steps", 0, "extra"], 1), "field-unknown"),
    ("field-unknown-coverage", _set(["meta", "coverage", "extra"], 1), "field-unknown"),
    ("field-unknown-section", _set(["sections", "roadmap", "extra"], 1), "field-unknown"),
    ("id-duplicate-node", _dup("nodes"), "id-duplicate"),
    ("id-duplicate-flow", _dup("flows"), "id-duplicate"),
    ("layer-undeclared-node", _set(["nodes", 0, "layer"], "nowhere"), "layer-undeclared"),
    ("path-invalid-files-dotdot", _set(["nodes", 0, "files", 0], "../x.py"), "path-invalid"),
    ("path-invalid-files-backslash", _set(["nodes", 0, "files", 0], "app\\orders\\api.py"), "path-invalid"),
    ("path-invalid-files-absolute", _set(["nodes", 0, "files", 0], "/etc/passwd"), "path-invalid"),
    ("path-invalid-files-empty", _set(["nodes", 0, "files", 0], ""), "path-invalid"),
    ("path-invalid-step", _set(["flows", 0, "steps", 1, "path"], "C:/x.py"), "path-invalid"),
    ("path-invalid-step-glob", _set(["flows", 0, "steps", 0, "path"], "web/*.js"), "path-invalid"),
    ("path-invalid-entrypoint", _set(["meta", "entrypoints", 0, "path"], "../x"), "path-invalid"),
    ("path-invalid-entrypoint-glob", _set(["meta", "entrypoints", 0, "path"], "app/**"), "path-invalid"),
    ("path-invalid-reading-order", _set(["reading_order", 0, "path"], "a//b"), "path-invalid"),
    ("path-invalid-reading-order-glob", _set(["reading_order", 0, "path"], "web/*.js"), "path-invalid"),
    ("path-missing-files", _set(["nodes", 0, "files", 0], "app/orders/gone.py"), "path-missing"),
    ("path-missing-files-wrong-case", _set(["nodes", 0, "files", 0], "app/orders/API.py"), "path-missing"),
    ("path-missing-step", _set(["flows", 0, "steps", 1, "path"], "app/orders/gone.py"), "path-missing"),
    ("path-missing-entrypoint", _set(["meta", "entrypoints", 0, "path"], "app/gone.py"), "path-missing"),
    ("path-missing-reading-order", _set(["reading_order", 0, "path"], "app/gone.py"), "path-missing"),
    ("glob-empty-files", _set(["nodes", 1, "files", 0], "app/menu/*.rb"), "glob-empty"),
    ("line-invalid-zero", _step_update(line=0), "line-invalid"),
    ("line-invalid-negative", _step_update(line=-4), "line-invalid"),
    ("line-invalid-beyond-file", _step_update(line=999), "line-invalid"),
    ("line-invalid-without-path", _drop_step_path, "line-invalid"),
    ("line-invalid-directory", _step_update(path="app/orders", line=1), "line-invalid"),
    ("line-invalid-binary", _step_update(path="app/menu/assets/croissant.png", line=1), "line-invalid"),
    ("edge-dangling-from", _set(["edges", 0, "from"], "ghost"), "edge-dangling"),
    ("edge-dangling-to", _set(["edges", 0, "to"], "ghost"), "edge-dangling"),
    ("edge-self", _set(["edges", 0, "to"], "storefront"), "edge-self"),
    ("node-orphan", _add_orphan, "node-orphan"),
    ("step-node-missing", _set(["flows", 0, "steps", 0, "node"], "ghost"), "step-node-missing"),
    ("flow-too-short", _one_step, "flow-too-short"),
    ("flow-too-short-empty", _set(["flows", 0, "steps"], []), "flow-too-short"),
]


def _empty_file(root):
    (root / "app/orders/api.py").write_text("", encoding="utf-8")


# (name, mutate_tree(root), expected_code): changes to files, not to the map.
TREE_MUTATIONS = [
    ("line-invalid-file-emptied", _empty_file, "line-invalid"),
]


def _copy(tmp_path):
    root = tmp_path / "proj"
    shutil.copytree(FIXTURE, root)
    return root


def _read(root):
    return json.loads((root / MAP_REL).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name,mutate,code", MAP_MUTATIONS, ids=[m[0] for m in MAP_MUTATIONS])
def test_map_mutation_is_caught(am, tmp_path, name, mutate, code):
    root = _copy(tmp_path)
    data = _read(root)
    mutate(data)
    problems = am.check_map(data, root)
    assert code in {p.code for p in problems}, [str(p) for p in problems]


@pytest.mark.parametrize("name,mutate,code", TREE_MUTATIONS, ids=[m[0] for m in TREE_MUTATIONS])
def test_tree_mutation_is_caught(am, tmp_path, name, mutate, code):
    root = _copy(tmp_path)
    mutate(root)
    problems = am.check_map(_read(root), root)
    assert code in {p.code for p in problems}, [str(p) for p in problems]


def test_every_code_has_a_mutation():
    covered = {m[2] for m in MAP_MUTATIONS} | {m[2] for m in TREE_MUTATIONS}
    assert covered == CODES


def test_guard_emits_no_codes_outside_the_list(am, tmp_path):
    root = _copy(tmp_path)
    emitted = set()
    for _, mutate, _ in MAP_MUTATIONS:
        data = _read(root)
        mutate(data)
        emitted |= {p.code for p in am.check_map(data, root)}
    assert emitted <= CODES
