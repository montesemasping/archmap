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


def _isolated(code_or_args, cwd, *, code=False):
    """Run Python isolated (-I) and without site (-S): the editable install is not importable."""
    cmd = [sys.executable, "-I", "-S"] + (["-c", code_or_args] if code else code_or_args)
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8")


@dist_only
def test_package_is_absent_without_the_bundle(tmp_path):
    # `-I` alone still sees the venv's editable install; `-I -S` is what makes the premise true
    res = _isolated("import archmap", tmp_path, code=True)
    assert res.returncode != 0
    assert "ModuleNotFoundError" in res.stderr


@dist_only
def test_bundle_runs_where_the_package_is_absent(tmp_path):
    proj = tmp_path / "proj"
    shutil.copytree(FIXTURE, proj)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    res = _isolated([str(DIST_FILE), "--version"], elsewhere)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == f"archmap {header_version()}"
    res = _isolated([str(DIST_FILE), "check", "--root", str(proj)], elsewhere)
    assert res.returncode == 0, res.stdout + res.stderr


@dist_only
def test_bundle_namespace_is_flagged(tmp_path):
    code = (
        "import runpy, sys\n"
        f"ns = runpy.run_path({str(DIST_FILE)!r}, run_name='x')\n"
        "import archmap\n"
        "assert ns['__bundled__'] is True and archmap.__bundled__ is True\n"
        "assert archmap.cli.__spec__.loader.__class__.__name__ == '_BundleFinder'\n"
        "print('ok')\n"
    )
    res = _isolated(code, tmp_path, code=True)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "ok"


@dist_only
def test_tracebacks_from_the_bundle_show_source_lines(tmp_path):
    code = (
        "import runpy, traceback\n"
        f"runpy.run_path({str(DIST_FILE)!r}, run_name='x')\n"
        "import archmap\n"
        "try:\n"
        "    archmap.guard._problem('no-such-code', '', '')\n"
        "except AssertionError:\n"
        "    print(traceback.format_exc())\n"
    )
    res = _isolated(code, tmp_path, code=True)
    assert res.returncode == 0, res.stderr
    assert "<archmap-bundle>/archmap.where" in res.stdout
    assert 'raise AssertionError(f"unregistered guard code' in res.stdout


@dist_only
def test_failed_bundle_import_leaves_no_trace(tmp_path):
    broken = DIST_FILE.read_text(encoding="utf-8").replace("'archmap.cli':", "'archmap.cli_x':", 1)
    assert broken != DIST_FILE.read_text(encoding="utf-8")
    path = tmp_path / "broken.py"
    path.write_text(broken, encoding="utf-8", newline="\n")
    code = (
        "import runpy, sys\n"
        f"try:\n    runpy.run_path({str(path)!r}, run_name='x')\n"
        "except ImportError:\n    pass\n"
        "else:\n    raise SystemExit('import should have failed')\n"
        "assert not any(n == 'archmap' or n.startswith('archmap.') for n in sys.modules), 'modules left'\n"
        "assert not any(getattr(f, '_archmap_bundle', False) for f in sys.meta_path), 'finder left'\n"
        "print('ok')\n"
    )
    res = _isolated(code, tmp_path, code=True)
    assert res.returncode == 0, res.stdout + res.stderr
    assert res.stdout.strip() == "ok"
