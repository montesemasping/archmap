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
