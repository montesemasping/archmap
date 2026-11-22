import json
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "bakery"
MAP_REL = "docs/architecture-map.json"


def load_fixture_map():
    with open(FIXTURE / MAP_REL, encoding="utf-8") as fh:
        return json.load(fh)


def test_bakery_is_clean(am):
    assert am.check_map(load_fixture_map(), FIXTURE) == []


def test_cli_check_on_bakery_exits_zero(run_cli):
    res = run_cli(["check", "--root", str(FIXTURE)])
    assert res.returncode == 0, res.stdout + res.stderr
    assert res.stdout == ""
    assert "no problems" in res.stderr


def test_unknown_schema_is_the_only_problem(am):
    data = load_fixture_map()
    data["$schema"] = "architecture-map/v1"
    problems = am.check_map(data, FIXTURE)
    assert [p.code for p in problems] == ["schema-unknown"]
    assert "archmap/1" in problems[0].message


@pytest.mark.parametrize("root_value", [[], "text", 5, None, True, {}, {"meta": {}}])
def test_missing_schema_is_the_only_problem(am, root_value):
    problems = am.check_map(root_value, FIXTURE)
    assert [p.code for p in problems] == ["schema-missing"]


def test_non_string_schema_is_unknown(am):
    data = load_fixture_map()
    data["$schema"] = ["archmap/1"]
    assert [p.code for p in am.check_map(data, FIXTURE)] == ["schema-unknown"]


def test_problems_are_sorted_by_where_then_code(am):
    data = load_fixture_map()
    data["nodes"][0]["layer"] = "nope"
    data["edges"][0]["to"] = "ghost"
    del data["meta"]["title"]
    problems = am.check_map(data, FIXTURE)
    keys = [(p.where, p.code) for p in problems]
    assert keys == sorted(keys)
    assert len(keys) >= 3


def test_where_uses_ids_and_indexes(am):
    data = load_fixture_map()
    data["nodes"][0]["files"][1] = "app/orders/nothing.py"
    data["flows"][0]["steps"][2]["node"] = "ghost"
    data["edges"][1]["to"] = "ghost"
    data["meta"]["layers"][0] = {"title": "no id"}
    wheres = {p.where for p in am.check_map(data, FIXTURE)}
    assert "nodes[orders-api].files[1]" in wheres
    assert "flows[checkout].steps[2].node" in wheres
    assert "edges[1].to" in wheres
    assert "meta.layers[0].id" in wheres


def test_node_without_string_id_is_addressed_by_index(am):
    data = load_fixture_map()
    data["nodes"][0]["id"] = 5
    wheres = {p.where for p in am.check_map(data, FIXTURE)}
    assert "nodes[0].id" in wheres


GARBAGE = [
    0, 1.5, -3, True, False, None, "", "text", [], [1, 2, 3], ["a"], {}, {"a": 1},
    [[]], [{}], [[[[]]]], {"a": {"b": {"c": []}}}, "\u0000", "\ud800", "a" * 5000,
]


def _all_targets(node, prefix=()):
    yield prefix
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _all_targets(v, prefix + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _all_targets(v, prefix + (i,))


def _clone(value):
    return json.loads(json.dumps(value))


def test_check_map_never_raises_on_garbage(am):
    base = load_fixture_map()
    for value in GARBAGE:
        assert isinstance(am.check_map(value, FIXTURE), list)
    for target in [t for t in _all_targets(base) if t]:
        for value in GARBAGE:
            data = _clone(base)
            cur = data
            for key in target[:-1]:
                cur = cur[key]
            cur[target[-1]] = value
            assert isinstance(am.check_map(data, FIXTURE), list), (target, value)


def test_check_map_never_raises_on_removed_values(am):
    base = load_fixture_map()
    for target in [t for t in _all_targets(base) if t]:
        data = _clone(base)
        cur = data
        for key in target[:-1]:
            cur = cur[key]
        if isinstance(cur, dict):
            del cur[target[-1]]
        else:
            cur.pop(target[-1])
        assert isinstance(am.check_map(data, FIXTURE), list), target


def test_unregistered_code_is_a_programming_error(am):
    guard = am.guard._Guard(FIXTURE)
    with pytest.raises(AssertionError):
        guard.add("foo-bar", "x", "nope")


def _sources():
    base = Path(__file__).parent.parent / "src" / "archmap"
    return {n: (base / n).read_text(encoding="utf-8") for n in ("guard.py", "secrets.py", "where.py")}


def test_every_code_literal_in_guard_source_is_registered(am):
    import re

    literals = set()
    for text in _sources().values():
        literals |= set(re.findall(r'(?:\.add|_problem)\(\s*"([A-Za-z0-9_-]+)"', text))
    assert literals, "scan found no code literals"
    assert literals <= set(am.guard.GUARD_CODES)


def test_problems_are_only_built_through_the_registry():
    import re

    constructions = sum(len(re.findall(r"(?<![A-Za-z_])Problem\(", t)) for t in _sources().values())
    assert constructions == 1  # the one inside _problem


def test_no_function_level_imports_between_guard_modules():
    for name, text in _sources().items():
        for line in text.splitlines():
            assert not line.startswith((" ", "	")) or "import " not in line.split("#")[0], (name, line)


def test_read_error_on_line_check_is_line_invalid(am, monkeypatch):
    def boom(path):
        raise OSError("denied")

    monkeypatch.setattr(am.guard, "count_lines", boom)
    problems = am.check_map(load_fixture_map(), FIXTURE)
    assert any(p.code == "line-invalid" and "cannot read" in p.message for p in problems)


def test_id_with_control_characters_falls_back_to_index(am):
    data = load_fixture_map()
    data["nodes"][0]["id"] = "evil\nid"
    data["nodes"][0]["files"].append("app/gone.py")
    problems = am.check_map(data, FIXTURE)
    for p in problems:
        assert "\n" not in p.where
        assert "\n" not in str(p)
    assert any(p.where == "nodes[0].files[3]" for p in problems)


def test_unknown_key_and_section_name_are_escaped(am):
    data = load_fixture_map()
    data["bad\nkey"] = 1
    data["sections"]["sec\ntion"] = {"title": "t"}
    problems = am.check_map(data, FIXTURE)
    assert problems
    for p in problems:
        assert "\n" not in p.where
        assert "\n" not in str(p)


def test_str_problem_escapes_control_characters(am):
    text = str(am.Problem("x", "a\nb", "m\r\u2028z"))
    assert "\n" not in text and "\r" not in text and "\u2028" not in text
    assert "\\u000a" in text


def _copy_fixture(tmp_path):
    import shutil

    root = tmp_path / "proj"
    shutil.copytree(FIXTURE, root)
    return root


def test_core_counts_binary_file_without_reading_it(am, tmp_path, monkeypatch):
    import builtins
    import io

    root = _copy_fixture(tmp_path)
    data = load_fixture_map()
    # the only step that reads files is checked once; drop its lines so nothing else opens files
    for flow in data["flows"]:
        for step in flow["steps"]:
            step.pop("line", None)
    real_open = builtins.open

    def guarded_open(file, *a, **kw):
        assert not str(file).endswith(".png"), "the binary file must not be opened"
        return real_open(file, *a, **kw)

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(io, "open", guarded_open)
    assert am.check_map(data, root) == []
    data["nodes"][1]["files"] = ["app/menu/*.py"]
    problems = am.check_map(data, root)
    assert [p.code for p in problems] == ["coverage-uncovered"]
    assert "croissant.png" in problems[0].message
    assert problems[0].where == "meta.coverage"


def test_core_literal_file_and_directory_entries(am, tmp_path):
    root = _copy_fixture(tmp_path)
    data = load_fixture_map()
    data["meta"]["coverage"] = {"core": ["app/orders/api.py", "app/menu"], "ignored": []}
    data["nodes"][0]["files"] = ["app/orders/api.py"]
    assert am.check_map(data, root) == []
    data["meta"]["coverage"]["core"] = ["app/orders/api.py/"]
    codes = [p.code for p in am.check_map(data, root)]
    assert "coverage-core-glob-empty" in codes


def test_malformed_coverage_is_not_double_reported(am):
    data = load_fixture_map()
    data["meta"]["coverage"] = {"core": "app/**"}
    codes = [p.code for p in am.check_map(data, FIXTURE)]
    assert codes == ["field-invalid"]


def test_uncovered_files_are_listed_deterministically(am, tmp_path):
    root = _copy_fixture(tmp_path)
    names = [f"f{n}.js" for n in (7, 3, 9, 1, 5, 10, 2, 8, 4, 6)]
    for name in names:
        (root / "web" / name).write_text("//", encoding="utf-8")
    problems = am.check_map(load_fixture_map(), root)
    assert len(problems) == 10 and {p.code for p in problems} == {"coverage-uncovered"}
    msgs = [p.message for p in problems]
    assert msgs == sorted(msgs)
    assert msgs == [p.message for p in am.check_map(load_fixture_map(), root)]
