"""Final-review hardening: secrets coverage, catch-all entries, depth caps, build refusal."""
import json
import shutil
import sys
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "bakery"
MAP_REL = "docs/architecture-map.json"
DEFAULT_OUT = "runtime/html-artifacts/architecture-map.html"
AWS_ID = "AKIA" + "ABCDEFGHIJKLMNOP"  # synthetic


def load_fixture_map():
    return json.loads((FIXTURE / MAP_REL).read_text(encoding="utf-8"))


def copy_project(tmp_path):
    dst = tmp_path / "proj"
    shutil.copytree(FIXTURE, dst)
    return dst


def write_map(project, data):
    (project / MAP_REL).write_text(json.dumps(data, indent=2), encoding="utf-8", newline="\n")


def _with_files_entry(entry):
    data = load_fixture_map()
    data["nodes"][0]["files"].append(entry)
    return data


# ---- catch-all coverage -------------------------------------------------------------


@pytest.mark.parametrize("entry", ["*", "**", "**/*", "**/*.py", "**/app/**"])
def test_catch_all_files_entry_is_path_invalid(am, entry):
    problems = am.check_map(_with_files_entry(entry), FIXTURE)
    broad = [p for p in problems if p.code == "path-invalid"]
    assert len(broad) == 1 and "too broad: a single entry may not cover the whole tree" in broad[0].message
    assert "glob-empty" not in {p.code for p in problems}


def test_catch_all_entry_does_not_cover_core_files(am):
    data = load_fixture_map()
    data["nodes"][0]["files"] = ["**"]
    codes = {p.code for p in am.check_map(data, FIXTURE)}
    assert "coverage-uncovered" in codes


def test_scoped_double_star_entry_is_still_fine(am):
    problems = am.check_map(_with_files_entry("app/**/*.py"), FIXTURE)
    assert not [p for p in problems if "too broad" in p.message]


def test_ignored_entries_removing_every_core_file(am):
    data = load_fixture_map()
    data["meta"]["coverage"]["ignored"].append({"glob": "**", "why": "everything"})
    hit = [p for p in am.check_map(data, FIXTURE) if p.code == "coverage-core-empty"]
    assert len(hit) == 1 and "ignored entries remove every core file" in hit[0].message


def test_ignoring_part_of_the_core_is_fine(am):
    assert am.check_map(load_fixture_map(), FIXTURE) == []


# ---- recursion and segment cap --------------------------------------------------------


def test_validate_caps_segment_count(am):
    assert am.paths.validate_rel_path("/".join(["a"] * 128)) is None
    msg = am.paths.validate_rel_path("/".join(["a"] * 129))
    assert msg and "128" in msg


def test_glob_match_with_many_double_stars_does_not_recurse(am):
    pattern = "**/" * 1200 + "x.py"
    assert am.paths.glob_match(pattern, "a/b/x.py") is True
    assert am.paths.glob_match(pattern, "a/b/y.py") is False
    assert am.paths.glob_match("a/" + "**/" * 1200 + "x", "a/" + "/".join(["d"] * 3000) + "/x") is True


@pytest.mark.parametrize(
    "pattern,rel,expected",
    [
        ("a/**/b", "a/b", True),
        ("a/**/b", "a/x/y/b", True),
        ("a/**", "a/x/y", True),
        ("a/**", "a", True),
        ("**/*.py", "x.py", True),
        ("**/*.py", "a/b/x.py", True),
        ("**/*.py", "a/b/x.js", False),
        ("a/*/b", "a/x/y/b", False),
        ("**/**/b", "b", True),
        ("a/**/b/**/c", "a/b/c", True),
        ("a/**/b/**/c", "a/c/b", False),
    ],
)
def test_glob_match_table(am, pattern, rel, expected):
    assert am.paths.glob_match(pattern, rel) is expected


def test_long_globs_yield_problems_not_exceptions(am):
    deep = "a/" + "**/" * 1200 + "x"
    data = load_fixture_map()
    data["nodes"][0]["files"].append(deep)
    data["meta"]["coverage"]["ignored"].append({"glob": deep, "why": "x"})
    data["meta"]["coverage"]["core"].append(deep)
    problems = am.check_map(data, FIXTURE)
    assert sum(p.code == "path-invalid" and "128" in p.message for p in problems) == 3


# ---- secrets ---------------------------------------------------------------------------


def test_allow_why_is_scanned(am):
    key = "ghp_" + "A1b2" * 10
    data = {
        "$schema": "archmap/1",
        "meta": {"secret_allow": [{"match": "password = devpass123", "why": "ci token " + key}]},
        "gotchas": ["password = devpass123"],
    }
    problems = am.find_secrets(data)
    assert [p.code for p in problems] == ["secret-suspect"]
    assert problems[0].where == "meta.secret_allow[0].why"
    assert key not in problems[0].message


def _synthetic(prefix, n, alphabet="aB3dE5gH7jK9"):
    return prefix + (alphabet * n)[:n]


NEW_PATTERNS = [
    ("sk_live", _synthetic("sk_live_", 24)),
    ("sk_test", _synthetic("sk_test_", 24)),
    ("rk_live", _synthetic("rk_live_", 24)),
    ("AIza", _synthetic("AIza", 35)),
    ("gho", _synthetic("gho_", 36)),
    ("ghs", _synthetic("ghs_", 36)),
    ("ghu", _synthetic("ghu_", 36)),
    ("ghr", _synthetic("ghr_", 36)),
    ("glpat", _synthetic("glpat-", 20, "aB3dE5gH7jK9_-")),
    ("ASIA", "ASIA" + "ABCDEFGH23456789"),
    ("npm", _synthetic("npm_", 36)),
    ("private-key-rsa", "-----BEGIN RSA PRIVATE KEY-----"),
    ("private-key-plain", "-----BEGIN PRIVATE KEY-----"),
    ("private-key-in-prose", "paste: -----BEGIN OPENSSH PRIVATE KEY----- then the body"),
]


def _scan(am, text):
    return am.find_secrets({"$schema": "archmap/1", "meta": {}, "gotchas": [text]})


@pytest.mark.parametrize("text", [t for _, t in NEW_PATTERNS], ids=[n for n, _ in NEW_PATTERNS])
def test_new_key_patterns_are_detected(am, text):
    problems = _scan(am, text)
    assert {p.code for p in problems} == {"secret-suspect"}
    assert any("key-prefix" in p.message for p in problems)
    assert text not in " ".join(p.message for p in problems)


def test_bare_pass_keyword_assignment_is_detected(am):
    problems = _scan(am, "DB_PASS=s3cr3tvalue")
    assert [p.code for p in problems] == ["secret-suspect"]
    assert "assignment" in problems[0].message
    assert [p.code for p in _scan(am, "pass: s3cr3tvalue")] == ["secret-suspect"]


@pytest.mark.parametrize(
    "text",
    [
        "bypass",
        "passport",
        "password reset flow",
        "compass",
        "bypass=abcdef123456",
        "passport: A1234567890X",
        "compass: abcdef123456",
        "pass: required",
        "ASIA is a continent",
        "ASIAPACIFICREGIONSERVICE1",
        "sk_live_ is the stripe prefix",
    ],
)
def test_new_rules_have_no_false_positives(am, text):
    assert _scan(am, text) == []


def test_suspect_id_falls_back_to_index_everywhere(am):
    data = load_fixture_map()
    data["nodes"][0]["id"] = AWS_ID
    data["nodes"][0]["extra"] = 1
    data["nodes"].append(dict(data["nodes"][0]))
    data["edges"][0]["to"] = AWS_ID
    data["flows"][0]["steps"][0]["node"] = AWS_ID
    problems = am.check_map(data, FIXTURE)
    assert any(p.code == "field-unknown" and p.where == "nodes[0].extra" for p in problems)
    assert any(p.code == "secret-suspect" and p.where == "nodes[0].id" for p in problems)
    assert any(p.code == "id-duplicate" for p in problems)
    for p in problems:
        assert AWS_ID not in str(p)


def test_suspect_unknown_key_is_redacted_in_where_and_message(am):
    data = load_fixture_map()
    data[AWS_ID] = 1
    data["nodes"][0][AWS_ID] = 2
    problems = [p for p in am.check_map(data, FIXTURE) if p.code == "field-unknown"]
    assert len(problems) == 2
    for p in problems:
        assert AWS_ID not in str(p)
        assert "'AKIA…'" in p.message


def test_plain_ids_and_keys_are_still_shown(am):
    data = load_fixture_map()
    data["nodes"][0]["extra"] = 1
    problems = am.check_map(data, FIXTURE)
    assert [(p.where, p.message) for p in problems] == [("nodes[orders-api].extra", "unknown field 'extra'")]


# ---- line-invalid wording ----------------------------------------------------------------


def test_non_utf8_file_is_not_called_binary(am, tmp_path):
    root = copy_project(tmp_path)
    (root / "app/orders/api.py").write_bytes(b"ab\xff\xfecd\n" * 40)
    (root / "app/orders/models.py").write_bytes(b"ab\x00cd\n")
    data = load_fixture_map()
    steps = data["flows"][0]["steps"]
    steps[1].update(path="app/orders/api.py", line=1)
    steps[0].update(path="app/orders/models.py", line=1)
    msgs = [p.message for p in am.check_map(data, root) if p.code == "line-invalid"]
    assert any("not valid UTF-8" in m and "api.py" in m for m in msgs)
    assert any("binary (NUL byte)" in m and "models.py" in m for m in msgs)


# ---- loader depth cap ------------------------------------------------------------------------


def _write_nested(tmp_path, depth):
    f = tmp_path / "m.json"
    f.write_text("[" * depth + "1" + "]" * depth, encoding="utf-8")
    return f


def test_nesting_up_to_200_is_loaded(am, tmp_path):
    assert am.load_map(_write_nested(tmp_path, 200)) is not None


@pytest.mark.parametrize("depth", [201, 600, 200000])
def test_nesting_deeper_than_200_is_json_invalid(am, tmp_path, depth):
    with pytest.raises(am.MapLoadError) as ei:
        am.load_map(_write_nested(tmp_path, depth) if depth < 5000 else _write_open(tmp_path, depth))
    assert ei.value.problem.code == "json-invalid"
    assert "nesting deeper than 200" in ei.value.problem.message


def _write_open(tmp_path, depth):
    f = tmp_path / "open.json"
    f.write_text("[" * depth, encoding="utf-8")
    return f


def test_deep_objects_count_too(am, tmp_path):
    f = tmp_path / "m.json"
    f.write_text('{"a":' * 201 + "1" + "}" * 201, encoding="utf-8")
    with pytest.raises(am.MapLoadError) as ei:
        am.load_map(f)
    assert "nesting deeper than 200" in ei.value.problem.message


# ---- build refuses secrets -------------------------------------------------------------------


def test_build_refuses_to_write_a_suspected_secret(run_cli, tmp_path):
    proj = copy_project(tmp_path)
    data = load_fixture_map()
    data["gotchas"].append("prod key " + AWS_ID)
    write_map(proj, data)
    res = run_cli(["build", "--root", str(proj)])
    assert res.returncode == 1
    assert "[secret-suspect]" in res.stdout
    assert "refusing to write HTML that would contain a suspected secret" in res.stderr
    assert not (proj / "runtime").exists()
    out = tmp_path / "explicit.html"
    res = run_cli(["build", "--root", str(proj), "-o", str(out)])
    assert res.returncode == 1 and not out.exists()


def test_check_still_reports_secrets_with_exit_one(run_cli, tmp_path):
    proj = copy_project(tmp_path)
    data = load_fixture_map()
    data["gotchas"].append("prod key " + AWS_ID)
    write_map(proj, data)
    res = run_cli(["check", "--root", str(proj)])
    assert res.returncode == 1
    assert AWS_ID not in res.stdout


# ---- internal errors -------------------------------------------------------------------------


@pytest.mark.parametrize("command", ["check", "build"])
def test_internal_error_exits_two(am, monkeypatch, capsys, tmp_path, command):
    proj = copy_project(tmp_path)

    def boom(data, root):
        raise RuntimeError("boom")

    monkeypatch.setattr(sys.modules[am.main.__module__], "check_map", boom)
    code = am.main([command, "--root", str(proj)])
    err = capsys.readouterr().err
    assert code == 2
    assert "archmap: internal error: RuntimeError: boom" in err
    assert "Traceback" not in err


# ---- template import ---------------------------------------------------------------------------


def test_unrelated_import_error_is_not_swallowed(am, monkeypatch):
    if getattr(am, "__bundled__", False):
        pytest.skip("the bundle has _bundled; there is no fallback to test")
    import importlib.abc
    import importlib.util

    class Loader(importlib.abc.Loader):
        def create_module(self, spec):
            return None

        def exec_module(self, module):
            raise ModuleNotFoundError("No module named 'elsewhere'", name="elsewhere")

    class Finder(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            if name == "archmap._bundled":
                return importlib.util.spec_from_loader(name, Loader())
            return None

    monkeypatch.setattr(sys, "meta_path", [Finder(), *sys.meta_path])
    with pytest.raises(ModuleNotFoundError) as ei:
        am.render_html({"$schema": "archmap/1"}, [])
    assert ei.value.name == "elsewhere"


def test_missing_bundled_module_falls_back_to_the_template_file(am):
    if getattr(am, "__bundled__", False):
        pytest.skip("the bundle has _bundled")
    html = am.render_html({"$schema": "archmap/1"}, [])
    assert "<html" in html.lower()
