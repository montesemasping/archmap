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
function mk(tag) {
  return {tag, children: [], attrs: {}, hidden: false, className: "", _text: "",
    set textContent(v) { this._text = String(v); }, get textContent() { return this._text; },
    appendChild(c) { this.children.push(c); return c; },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    set href(v) { this.attrs.href = String(v); }, get href() { return this.attrs.href; }};
}
const ids = {};
for (const id of ["title", "problems", "nodes", "flows", "sections"]) ids[id] = mk("div");
ids["archmap-data"] = mk("script");
ids["archmap-data"]._text = data;
global.document = {title: "", getElementById: (id) => ids[id], createElement: mk};
new Function(code)();
const anchors = [];
(function walk(n) { if (n.tag === "a") anchors.push(n.attrs); n.children.forEach(walk); })({tag: "root", children: Object.values(ids)});
console.log(JSON.stringify({anchors, problems: ids.problems.children.length, title: document.title}));
"""


def run_viewer(tmp_path, am, data, problems=()):
    html = tmp_path / "page.html"
    html.write_text(am.render_html(data, list(problems)), encoding="utf-8", newline="\n")
    runner = tmp_path / "runner.js"
    runner.write_text(RUNNER, encoding="utf-8")
    res = subprocess.run(["node", str(runner), str(html)], capture_output=True, text=True, encoding="utf-8")
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
    res = subprocess.run(["node", str(runner), str(page)], capture_output=True, text=True, encoding="utf-8")
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout)["anchors"] == []
