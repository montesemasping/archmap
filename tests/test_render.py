import json
import re

import pytest

SECTION_RE = re.compile(r'<script id="archmap-data" type="application/json">(.*?)</script>', re.S)
EVIL = "</script><!--  &<>"


def base_map(**meta):
    return {
        "$schema": "archmap/1",
        "meta": {"project": "p", "title": "T", **meta},
        "nodes": [{"id": "a", "label": "A", "layer": "x", "files": ["src/a.py", "src/*.py", "../bad.py"]}],
        "edges": [],
        "flows": [],
    }


def extract(html):
    return json.loads(SECTION_RE.search(html).group(1))


def test_round_trip_with_hostile_strings(am):
    data = base_map(summary=EVIL)
    data["nodes"][0]["summary"] = EVIL
    data["flows"] = [{"id": "f", "title": "F", "steps": [{"node": "a", "note": EVIL}]}]
    data["sections"] = {"s": {"title": "S", "body": [EVIL, {"k": EVIL}]}}
    problem = am.Problem("field-invalid", "x", EVIL)
    html = am.render_html(data, [problem])
    payload = extract(html)
    assert payload["map"] == data
    assert payload["problems"] == [str(problem)]
    assert payload["version"] == am.__version__
    template = am.render._template_text()
    assert html.count("</script>") == template.count("</script>")
    assert html.count("<!--") == template.count("<!--")
    assert " " not in html and " " not in html


def test_backslashes_survive(am):
    data = base_map(summary="a\\1 \\n \\u0041")
    assert extract(am.render_html(data, []))["map"] == data


def test_links_empty_without_source_url(am):
    assert extract(am.render_html(base_map(), []))["links"] == {}


def test_links_ignore_non_http_url(am):
    data = base_map(source_url="javascript:alert(1)//{path}")
    assert extract(am.render_html(data, []))["links"] == {}


def test_links_computed(am):
    data = base_map(
        source_url="https://example.com/b/{path}#L{line}",
        entrypoints=[{"path": "main.py"}, {"what": "no path"}],
    )
    data["reading_order"] = [{"path": "docs/read me.md"}]
    data["gotchas"] = ["plain", {"text": "t", "path": "g.py"}]
    data["flows"] = [{"id": "f", "title": "F", "steps": [
        {"node": "a", "path": "s.py", "line": 4}, {"node": "a", "path": "t.py", "line": 0},
        {"node": "a", "path": "../x.py", "line": 1}]}]
    links = extract(am.render_html(data, []))["links"]
    assert links["src/a.py"] == "https://example.com/b/src/a.py"
    assert "src/*.py" not in links and "../bad.py" not in links
    assert links["main.py"] == "https://example.com/b/main.py"
    assert links["docs/read me.md"] == "https://example.com/b/docs/read%20me.md"
    assert links["g.py"] == "https://example.com/b/g.py"
    assert links["s.py#4"] == "https://example.com/b/s.py#L4"
    assert links["s.py"] == "https://example.com/b/s.py"
    assert "t.py#0" not in links and "t.py" in links
    assert "../x.py" not in links


@pytest.mark.parametrize("bad", [
    {}, {"meta": 1}, {"meta": {"source_url": "https://e/{path}"}, "nodes": [1, {"files": "x"}, {"files": [3, None]}],
                      "flows": [None, {"steps": [5, {"path": 3, "line": "x"}]}], "gotchas": "s", "reading_order": [1]},
])
def test_render_never_raises(am, bad):
    assert isinstance(am.render_html(bad, []), str)


def test_source_link_with_line(am):
    assert am.source_link("https://h/{path}#L{line}", "a/b.py", 7) == "https://h/a/b.py#L7"


@pytest.mark.parametrize("template, expected", [
    ("https://h/{path}#L{line}", "https://h/a/b.py"),
    ("https://h/{path}#{line}", "https://h/a/b.py"),
    ("https://h/{path}?plain=1#L{line}", "https://h/a/b.py?plain=1"),
    ("https://h/{path}?l={line}", "https://h/a/b.py?l="),
])
def test_source_link_without_line(am, template, expected):
    assert am.source_link(template, "a/b.py", None) == expected


def test_source_link_template_without_line(am):
    assert am.source_link("https://h/{path}", "a.py", 3) == "https://h/a.py"
    assert am.source_link("https://h/{path}", "a.py", None) == "https://h/a.py"


def test_source_link_encodes_and_keeps_other_braces(am):
    assert am.source_link("https://h/{ref}/{path}", "my dir/a#b.py", None) == "https://h/{ref}/my%20dir/a%23b.py"


def test_render_replaces_nan_with_null(am):
    data = base_map(x=float("nan"), y=[float("inf"), float("-inf"), 1.5])
    payload = extract(am.render_html(data, []))
    assert payload["map"]["meta"]["x"] is None
    assert payload["map"]["meta"]["y"] == [None, None, 1.5]


def test_render_lone_surrogate_round_trips(am):
    data = base_map(summary="a\ud800b")
    html = am.render_html(data, [])
    html.encode("utf-8")
    assert extract(html)["map"] == data
