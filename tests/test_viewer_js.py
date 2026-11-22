import importlib.resources
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURE_MAP = Path(__file__).parent / "fixtures" / "bakery" / "docs" / "architecture-map.json"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

RUNNER = r"""
const fs = require("fs");
const html = fs.readFileSync(process.argv[2], "utf8");
const data = /<script id="archmap-data"[^>]*>([\s\S]*?)<\/script>/.exec(html)[1];
const code = /<script>([\s\S]*?)<\/script>/.exec(html)[1];
const SVG_NS = "http://www.w3.org/2000/svg";
function mk(tag) {
  const listeners = {};
  const o = {tag, children: [], attrs: {}, hidden: false, className: "", _text: "", value: "", disabled: false,
    clientWidth: 0, clientHeight: 0, offsetWidth: 0, offsetHeight: 0, offsetLeft: 0, offsetTop: 0, listeners,
    style: {setProperty(k, v) { this[k] = v; }},
    classList: {_s: new Set(), toggle(c, on) { on ? this._s.add(c) : this._s.delete(c); }, add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); }},
    set textContent(v) { this._text = String(v); this.children = []; }, get textContent() { return this._text; },
    appendChild(c) { this.children.push(c); return c; },
    removeChild(c) { this.children = this.children.filter((x) => x !== c); return c; },
    setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return this.attrs[k] === undefined ? null : this.attrs[k]; },
    set href(v) { this.attrs.href = String(v); }, get href() { return this.attrs.href; },
    addEventListener(t, f) { (listeners[t] = listeners[t] || []).push(f); },
    getBoundingClientRect() { return {left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0}; },
    focus() {}, blur() {}};
  return o;
}
const ids = {};
const bodyIds = [...html.matchAll(/<[a-z0-9]+[^>]*\sid="([^"]+)"/g)].map((m) => m[1]);
for (const id of bodyIds) ids[id] = mk("div");
ids["archmap-data"]._text = data;
const docListeners = {};
global.document = {title: "", activeElement: null, documentElement: mk("html"), getElementById: (id) => ids[id],
  createElement: mk, createElementNS: (ns, tag) => mk(tag), createTextNode: (t) => { const n = mk("#text"); n._text = t; return n; },
  addEventListener(t, f) { (docListeners[t] = docListeners[t] || []).push(f); }};
const winListeners = {};
global.window = {matchMedia: () => ({matches: process.argv[3] === "dark"}), addEventListener(t, f) { (winListeners[t] = winListeners[t] || []).push(f); }};
global.requestAnimationFrame = (f) => f();
new Function(code)();

const root = {tag: "root", children: Object.values(ids)};
const anchors = [], badges = new Set(), failures = [];
function walk(n, fn) { fn(n); n.children.forEach((c) => walk(c, fn)); }
function collect() {
  walk(root, (n) => {
    if (n.tag === "a") anchors.push(n.attrs);
    if (n.className === "sn" && n._text) badges.add(n._text);
    if ((n._text || "").startsWith("Could not render")) failures.push(n._text);
  });
}
function fire(n, type, ev) { for (const f of (n.listeners[type] || [])) f(Object.assign({stopPropagation() {}, preventDefault() {}}, ev)); }
function fireAll(map, type, ev) { for (const f of (map[type] || [])) f(Object.assign({preventDefault() {}}, ev)); }
collect();
const boxes = [];
walk(ids.cols, (n) => { if (n.className === "node") boxes.push(n); });
const options = ids.flow.children.map((o) => o.attrs.value).filter(Boolean);
for (const v of options) { ids.flow.value = v; fire(ids.flow, "change"); collect(); }
for (const b of boxes) { fire(b, "click"); collect(); fireAll(docListeners, "keydown", {key: "Enter"}); }
ids.search.value = "a"; fire(ids.search, "input");
fire(ids.theme, "click"); fire(ids.theme, "click");
for (const b of ids.layers.children) { fire(b, "click"); fire(b, "click"); }
for (const id of ["zin", "zout", "zfit"]) fire(ids[id], "click");
fire(ids.viewport, "pointerdown", {clientX: 0, clientY: 0, button: 0});
fireAll(winListeners, "pointermove", {clientX: 40, clientY: 9});
fireAll(winListeners, "pointerup", {});
fire(ids.viewport, "wheel", {deltaY: -1, clientX: 5, clientY: 5});
fire(ids.viewport, "click");
fire(ids.reset, "click");
fireAll(docListeners, "keydown", {key: "Escape"});
fireAll(docListeners, "keydown", {key: "/"});
fireAll(winListeners, "resize", {});
collect();
console.log(JSON.stringify({anchors, problems: ids.problems.children.length, title: document.title, failures,
  theme: document.documentElement.attrs["data-theme"], badges: [...badges].sort(), nodes: boxes.length,
  edges: ids.edges.children.length}));
"""


def run_viewer(tmp_path, am, data, problems=(), scheme="light"):
    html = tmp_path / "page.html"
    html.write_text(am.render_html(data, list(problems)), encoding="utf-8", newline="\n")
    runner = tmp_path / "runner.js"
    runner.write_text(RUNNER, encoding="utf-8")
    res = subprocess.run(["node", str(runner), str(html), scheme], capture_output=True, text=True, encoding="utf-8")
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def test_viewer_survives_malformed_map(am, tmp_path):
    data = {"$schema": "archmap/1", "meta": {"title": "T"}, "nodes": [None, 5, "x"],
            "flows": [None], "sections": {"a": 3}}
    problem = am.Problem("field-invalid", "nodes[0]", "bad")
    out = run_viewer(tmp_path, am, data, [problem])
    assert out["problems"] == 2 and out["title"] == "T"


def test_viewer_survives_odd_shapes(am, tmp_path):
    data = {"meta": 3, "nodes": {"a": 1}, "flows": [{"steps": [None, 1, {"path": 3}]}, {"steps": "x"}],
            "sections": {"s": None, "t": {"body": {"k": [None, {"z": 1}]}}}}
    run_viewer(tmp_path, am, data)


def test_viewer_links_files_and_steps(am, tmp_path):
    data = json.loads(FIXTURE_MAP.read_text(encoding="utf-8"))
    out = run_viewer(tmp_path, am, data)
    assert out["failures"] == [] and out["nodes"] == 4 and out["badges"] == ["1", "2", "3"]
    hrefs = [a["href"] for a in out["anchors"]]
    assert "https://example.com/bakery/blob/main/app/orders/api.py#L6" in hrefs
    assert "https://example.com/bakery/blob/main/app/orders/api.py" in hrefs
    for a in out["anchors"]:
        assert a["rel"] == "noopener noreferrer" and a["target"] == "_blank"
        assert re.match(r"https?://", a["href"])


def test_viewer_rejects_unsafe_link_values(am, tmp_path):
    data = {"meta": {"source_url": "https://e/{path}"}, "nodes": [{"id": "a", "files": ["f.py"]}]}
    html = am.render_html(data, [])
    html = html.replace("https://e/f.py", "javascript:alert(1)")
    page = tmp_path / "p.html"
    page.write_text(html, encoding="utf-8", newline="\n")
    runner = tmp_path / "r.js"
    runner.write_text(RUNNER, encoding="utf-8")
    res = subprocess.run(["node", str(runner), str(page), "light"], capture_output=True, text=True, encoding="utf-8")
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout)["anchors"] == []


def test_viewer_runs_with_lone_surrogate(am, tmp_path):
    data = {"meta": {"title": "a\ud800b"}, "nodes": [{"id": "n", "summary": "\ud800"}]}
    out = run_viewer(tmp_path, am, data)
    assert out["title"]


def test_viewer_theme_follows_color_scheme(am, tmp_path):
    data = json.loads(FIXTURE_MAP.read_text(encoding="utf-8"))
    assert run_viewer(tmp_path, am, data, scheme="dark")["theme"] == "dark"
    assert run_viewer(tmp_path, am, data, scheme="light")["theme"] == "light"


def test_built_page_has_data_block_once(am):
    data = json.loads(FIXTURE_MAP.read_text(encoding="utf-8"))
    html = am.render_html(data, [])
    assert html.count('<script id="archmap-data"') == 1
    assert "/*__ARCHMAP_DATA__*/" not in html
    assert (importlib.resources.files("archmap") / "template.html").read_text(encoding="utf-8").count("/*__ARCHMAP_DATA__*/") == 1
