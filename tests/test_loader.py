import json

import pytest


def test_problem_str_and_frozen(am):
    p = am.Problem(code="x-y", where="a.json", message="bad thing")
    assert str(p) == "a.json: bad thing [x-y]"
    with pytest.raises(Exception):
        p.code = "other"


def test_load_valid_with_bom_and_crlf(am, tmp_path):
    f = tmp_path / "map.json"
    text = '{\r\n  "$schema": "archmap/1",\r\n  "nodes": []\r\n}\r\n'
    f.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
    data = am.load_map(f)
    assert data == {"$schema": "archmap/1", "nodes": []}


def test_load_accepts_str_path_and_non_object_root(am, tmp_path):
    f = tmp_path / "m.json"
    f.write_text("[1, 2]", encoding="utf-8")
    assert am.load_map(str(f)) == [1, 2]


def test_load_non_ascii(am, tmp_path):
    f = tmp_path / "m.json"
    f.write_text(json.dumps({"t": "карта"}, ensure_ascii=False), encoding="utf-8")
    assert am.load_map(f) == {"t": "карта"}


def test_invalid_json_reports_position(am, tmp_path):
    f = tmp_path / "m.json"
    f.write_text('{\n  "a": 1,\n  "b": ,\n}\n', encoding="utf-8")
    with pytest.raises(am.MapLoadError) as ei:
        am.load_map(f)
    p = ei.value.problem
    assert p.code == "json-invalid"
    assert p.where == f"{f}:3:8"
    assert str(ei.value) == str(p)


def test_missing_file(am, tmp_path):
    f = tmp_path / "nope.json"
    with pytest.raises(am.MapLoadError) as ei:
        am.load_map(f)
    assert ei.value.problem.code == "map-missing"
    assert str(f) in ei.value.problem.where


def test_directory_is_map_missing(am, tmp_path):
    with pytest.raises(am.MapLoadError) as ei:
        am.load_map(tmp_path)
    assert ei.value.problem.code == "map-missing"


def test_invalid_utf8_is_json_invalid(am, tmp_path):
    f = tmp_path / "m.json"
    f.write_bytes(b'{"a": "\xff"}')
    with pytest.raises(am.MapLoadError) as ei:
        am.load_map(f)
    assert ei.value.problem.code == "json-invalid"


def test_deeply_nested_is_json_invalid(am, tmp_path):
    f = tmp_path / "m.json"
    f.write_text("[" * 200000, encoding="utf-8")
    with pytest.raises(am.MapLoadError) as ei:
        am.load_map(f)
    assert ei.value.problem.code == "json-invalid"
    assert ei.value.problem.where == str(f)


def test_huge_integer_is_json_invalid(am, tmp_path):
    f = tmp_path / "m.json"
    f.write_text("1" * 5000, encoding="utf-8")
    with pytest.raises(am.MapLoadError) as ei:
        am.load_map(f)
    assert ei.value.problem.code == "json-invalid"
    assert ei.value.problem.where == str(f)


def test_nul_in_path_is_map_missing(am, tmp_path):
    with pytest.raises(am.MapLoadError) as ei:
        am.load_map(str(tmp_path / "a\x00b.json"))
    assert ei.value.problem.code == "map-missing"
