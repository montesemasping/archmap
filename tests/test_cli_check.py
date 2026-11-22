import json
import shutil
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "bakery"
MAP_REL = "docs/architecture-map.json"


def copy_project(tmp_path):
    dst = tmp_path / "proj"
    shutil.copytree(FIXTURE, dst)
    return dst


def edit_map(project, fn):
    path = project / MAP_REL
    data = json.loads(path.read_text(encoding="utf-8"))
    fn(data)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8", newline="\n")


def test_broken_map_exits_one_with_problem_line(run_cli, tmp_path):
    proj = copy_project(tmp_path)
    edit_map(proj, lambda d: d["nodes"][0]["files"].append("app/orders/gone.py"))
    res = run_cli(["check", "--root", str(proj)])
    assert res.returncode == 1
    assert "[path-missing]" in res.stdout
    assert "nodes[orders-api].files[3]" in res.stdout
    assert res.stderr.strip() == "1 problem(s)"


def test_root_from_another_cwd(run_cli, tmp_path):
    proj = copy_project(tmp_path)
    other = tmp_path / "elsewhere"
    other.mkdir()
    res = run_cli(["check", "--root", str(proj)], cwd=other)
    assert res.returncode == 0, res.stdout + res.stderr


def test_default_root_is_cwd(run_cli, tmp_path):
    proj = copy_project(tmp_path)
    res = run_cli(["check"], cwd=proj)
    assert res.returncode == 0, res.stdout + res.stderr


def test_relative_map_resolves_against_cwd(run_cli, tmp_path):
    proj = copy_project(tmp_path)
    other = tmp_path / "elsewhere"
    other.mkdir()
    shutil.copy(proj / MAP_REL, other / "my-map.json")
    res = run_cli(["check", "my-map.json", "--root", str(proj)], cwd=other)
    assert res.returncode == 0, res.stdout + res.stderr


def test_missing_map_exits_two(run_cli, tmp_path):
    res = run_cli(["check", "--root", str(tmp_path)])
    assert res.returncode == 2
    assert "cannot read map file" in res.stderr
    assert res.stdout == ""


def test_invalid_json_exits_two(run_cli, tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / MAP_REL).write_text("{not json", encoding="utf-8")
    res = run_cli(["check", "--root", str(tmp_path)])
    assert res.returncode == 2
    assert "[json-invalid]" in res.stderr


def test_usage_error_exits_two(run_cli):
    assert run_cli(["check", "--bogus"]).returncode == 2
    assert run_cli([]).returncode == 2


def test_version(run_cli, am):
    res = run_cli(["--version"])
    assert res.returncode == 0
    assert res.stdout.strip() == f"archmap {am.__version__}"


def test_bom_and_crlf_map(run_cli, tmp_path):
    proj = copy_project(tmp_path)
    path = proj / MAP_REL
    text = path.read_text(encoding="utf-8")
    path.write_bytes(b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8"))
    res = run_cli(["check", "--root", str(proj)])
    assert res.returncode == 0, res.stdout + res.stderr


def test_binary_file_is_fine_but_line_on_it_is_invalid(run_cli, tmp_path):
    proj = copy_project(tmp_path)
    assert run_cli(["check", "--root", str(proj)]).returncode == 0

    def add_line(d):
        d["flows"][0]["steps"][2]["path"] = "app/menu/assets/croissant.png"
        d["flows"][0]["steps"][2]["line"] = 1

    edit_map(proj, add_line)
    res = run_cli(["check", "--root", str(proj)])
    assert res.returncode == 1
    assert "[line-invalid]" in res.stdout


def test_non_ascii_output_does_not_crash(run_cli, tmp_path):
    proj = copy_project(tmp_path)
    edit_map(proj, lambda d: d["nodes"][0]["files"].append("app/путь.py"))
    res = run_cli(["check", "--root", str(proj)])
    assert res.returncode == 1
    assert "[path-missing]" in res.stdout
