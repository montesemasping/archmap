import json
import shutil
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "bakery"
MAP_REL = "docs/architecture-map.json"
DEFAULT_OUT = "runtime/html-artifacts/architecture-map.html"


def copy_project(tmp_path):
    dst = tmp_path / "proj"
    shutil.copytree(FIXTURE, dst)
    return dst


def edit_map(project, fn):
    path = project / MAP_REL
    data = json.loads(path.read_text(encoding="utf-8"))
    fn(data)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8", newline="\n")


def test_build_default_path(run_cli, tmp_path):
    proj = copy_project(tmp_path)
    res = run_cli(["build", "--root", str(proj)])
    assert res.returncode == 0, res.stdout
    out = proj / DEFAULT_OUT
    assert out.is_file()
    text = out.read_bytes().decode("utf-8")
    assert "Bakery ordering app" in text and "\r" not in text
    assert "no problems" in res.stderr and "architecture-map.html" in res.stderr
    assert res.stdout == ""


def test_build_broken_map_still_writes(run_cli, tmp_path):
    proj = copy_project(tmp_path)
    edit_map(proj, lambda d: d["nodes"][0]["files"].append("app/orders/gone.py"))
    res = run_cli(["build", "--root", str(proj)])
    assert res.returncode == 1
    assert "[path-missing]" in res.stdout
    assert "path-missing" in (proj / DEFAULT_OUT).read_text(encoding="utf-8")


def test_build_unknown_schema_writes_nothing(run_cli, tmp_path):
    proj = copy_project(tmp_path)
    edit_map(proj, lambda d: d.update({"$schema": "other/9"}))
    res = run_cli(["build", "--root", str(proj)])
    assert res.returncode == 1
    assert "[schema-unknown]" in res.stdout
    assert not (proj / "runtime").exists()


def test_build_output_in_new_nested_dir(run_cli, tmp_path):
    proj = copy_project(tmp_path)
    out = tmp_path / "a" / "b" / "map.html"
    res = run_cli(["build", "--root", str(proj), "-o", str(out)])
    assert res.returncode == 0
    assert out.is_file()


def test_build_relative_output_resolves_against_cwd(run_cli, tmp_path):
    proj = copy_project(tmp_path)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    res = run_cli(["build", "--root", str(proj), "-o", "out/m.html"], cwd=cwd)
    assert res.returncode == 0
    assert (cwd / "out" / "m.html").is_file()
    assert not (proj / "out").exists()


def test_build_missing_map_exits_two(run_cli, tmp_path):
    res = run_cli(["build", "--root", str(tmp_path)])
    assert res.returncode == 2
    assert not (tmp_path / "runtime").exists()


def test_build_missing_root_exits_two(run_cli, tmp_path):
    assert run_cli(["build", "--root", str(tmp_path / "nope")]).returncode == 2


def test_build_malformed_map_round_trips(run_cli, tmp_path):
    import re

    proj = copy_project(tmp_path)
    def mangle(d):
        d["nodes"] = [None, 5, "x"]
        d["flows"] = [None]
        d["sections"] = {"a": 3}
    edit_map(proj, mangle)
    res = run_cli(["build", "--root", str(proj)])
    assert res.returncode == 1
    text = (proj / DEFAULT_OUT).read_text(encoding="utf-8")
    raw = re.search(r'<script id="archmap-data" type="application/json">(.*?)</script>', text, re.S).group(1)
    payload = json.loads(raw)
    assert payload["map"]["nodes"] == [None, 5, "x"]
    assert payload["map"]["sections"] == {"a": 3}
    assert payload["problems"]


def test_build_lone_surrogate_does_not_crash(run_cli, tmp_path):
    proj = copy_project(tmp_path)
    path = proj / MAP_REL
    text = path.read_text(encoding="utf-8").replace('"Bakery ordering app"', r'"Bakery \ud800 app"')
    path.write_text(text, encoding="utf-8", newline="\n")
    res = run_cli(["build", "--root", str(proj)])
    assert res.returncode in (0, 1), res.stderr
    assert "Traceback" not in res.stderr
    assert (proj / DEFAULT_OUT).is_file()


def test_build_nan_map_exits_two(run_cli, tmp_path):
    proj = copy_project(tmp_path)
    path = proj / MAP_REL
    text = path.read_text(encoding="utf-8").replace('"Bakery ordering app"', "NaN")
    path.write_text(text, encoding="utf-8", newline="\n")
    res = run_cli(["build", "--root", str(proj)])
    assert res.returncode == 2
    assert "[json-invalid]" in res.stderr
    assert not (proj / "runtime").exists()
