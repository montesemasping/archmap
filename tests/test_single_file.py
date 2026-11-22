import ast
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "bakery"
DIST_FILE = ROOT / "dist" / "archmap.py"
BUILD = ROOT / "tools" / "build_single.py"

dist_only = pytest.mark.skipif(
    __import__("os").environ.get("ARCHMAP_IMPL") != "dist", reason="needs ARCHMAP_IMPL=dist"
)


def header_version() -> str:
    first = DIST_FILE.read_text(encoding="utf-8").splitlines()[0]
    match = re.match(r"# archmap (\S+) – single-file build\. DO NOT EDIT; built from archmap v(\S+)\.$", first)
    assert match and match.group(1) == match.group(2), first
    return match.group(1)


def test_build_is_deterministic(tmp_path):
    outs = []
    for name in ("a.py", "b.py"):
        out = tmp_path / name
        subprocess.run([sys.executable, str(BUILD), "-o", str(out)], check=True, capture_output=True)
        outs.append(out.read_bytes())
    assert outs[0] == outs[1]
    assert b"\r" not in outs[0]
    compile(outs[0].decode("utf-8"), "archmap.py", "exec")


@dist_only
def test_loaded_from_the_bundle(am, dist_bundle):
    assert am.__bundled__ is True
    assert Path(dist_bundle.__file__).resolve() == DIST_FILE.resolve()


@dist_only
def test_version_matches_header(run_cli):
    res = run_cli(["--version"])
    assert res.returncode == 0
    assert res.stdout.strip() == f"archmap {header_version()}"


@dist_only
def test_check_runs_outside_the_repo(run_cli, tmp_path):
    proj = tmp_path / "proj"
    shutil.copytree(FIXTURE, proj)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    res = run_cli(["check", "--root", str(proj)], cwd=elsewhere)
    assert res.returncode == 0, res.stdout + res.stderr


@dist_only
def test_finder_claims_only_archmap_names(am, dist_bundle):
    finder = sys.meta_path[0]
    assert getattr(finder, "_archmap_bundle", False)
    assert finder.find_spec("json") is None
    assert finder.find_spec("archmap_other") is None
    assert finder.find_spec("archmap.cli") is not None


def _check_imports(source: str, label: str) -> None:
    stdlib = set(sys.stdlib_module_names)
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            tops = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            tops = [(node.module or "").split(".")[0]]
        else:
            continue
        for top in tops:
            assert top in stdlib or top == "archmap", f"{label}: non-stdlib import {top!r}"


@dist_only
def test_bundle_imports_only_stdlib(dist_bundle):
    _check_imports(DIST_FILE.read_text(encoding="utf-8"), "dist/archmap.py")
    assert dist_bundle._SOURCES
    for name, source in dist_bundle._SOURCES.items():
        _check_imports(source, name)


@dist_only
def test_embedded_template_matches_the_source(am):
    from archmap import _bundled

    source = (ROOT / "src" / "archmap" / "template.html").read_bytes().decode("utf-8")
    assert _bundled.TEMPLATE == source.replace("\r\n", "\n")
