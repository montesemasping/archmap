import pytest


def touch(root, rel, data=b"x"):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


# validate_rel_path

@pytest.mark.parametrize(
    "bad",
    ["", "../a", "a/../b", "a/..", "/abs", "C:/x", "C:x", "a" + chr(92) + "b", "a**b", "**a/b", "a/b**"],
)
def test_validate_rejects(am, bad):
    msg = am.paths.validate_rel_path(bad)
    assert isinstance(msg, str) and msg


@pytest.mark.parametrize(
    "good", ["a", "src/a.py", "src/", "src/**/*.py", "**", "a/**/b", "x?.py", "a/b"]
)
def test_validate_accepts(am, good):
    assert am.paths.validate_rel_path(good) is None


# exists_exact

def test_exists_exact_file_dir_none(am, tmp_path):
    touch(tmp_path, "app/x.py")
    e = am.paths.exists_exact
    assert e(tmp_path, "app/x.py") == "file"
    assert e(tmp_path, "app") == "dir"
    assert e(tmp_path, "app/") == "dir"
    assert e(tmp_path, "app/y.py") is None
    assert e(tmp_path, "app/x.py/more") is None


def test_exists_exact_is_case_sensitive(am, tmp_path):
    touch(tmp_path, "app/x.py")
    assert am.paths.exists_exact(tmp_path, "App/x.py") is None
    assert am.paths.exists_exact(tmp_path, "app/X.py") is None


# is_glob

def test_is_glob(am):
    assert am.paths.is_glob("a/*.py")
    assert am.paths.is_glob("a?")
    assert not am.paths.is_glob("a/b.py")
    assert not am.paths.is_glob("a[1]")


# glob_match

@pytest.mark.parametrize(
    "pat,rel,expected",
    [
        ("src/*.py", "src/a.py", True),
        ("src/*.py", "src/x/a.py", False),
        ("src/**/*.py", "src/a.py", True),
        ("src/**/*.py", "src/x/y/b.py", True),
        ("src/**/*.py", "lib/a.py", False),
        ("**", "a/b/c", True),
        ("**/a.py", "a.py", True),
        ("**/a.py", "x/y/a.py", True),
        ("a/**", "a", True),
        ("a?c", "abc", True),
        ("a?c", "ac", False),
        ("a?c", "a/c", False),
        ("*.py", "A.PY", False),
        ("a[1].py", "a[1].py", True),
        ("a[1].py", "a1.py", False),
        ("a.b", "aXb", False),
        ("a*b*c", "aXXbYYc", True),
        ("a*b*c", "aXXbYY", False),
    ],
)
def test_glob_match(am, pat, rel, expected):
    assert am.paths.glob_match(pat, rel) is expected


# expand_glob

def test_expand_glob(am, tmp_path):
    touch(tmp_path, "src/a.py")
    touch(tmp_path, "src/x/y/b.py")
    touch(tmp_path, "src/c.txt")
    touch(tmp_path, "src/__pycache__/d.py")
    touch(tmp_path, "src/node_modules/e.py")
    touch(tmp_path, "src/.git/f.py")
    touch(tmp_path, "other/z.py")
    assert am.paths.expand_glob(tmp_path, "src/**/*.py") == ["src/a.py", "src/x/y/b.py"]
    assert am.paths.expand_glob(tmp_path, "src/*.py") == ["src/a.py"]
    assert am.paths.expand_glob(tmp_path, "**/*.py") == ["other/z.py", "src/a.py", "src/x/y/b.py"]


def test_expand_glob_missing_prefix_and_wrong_case(am, tmp_path):
    touch(tmp_path, "src/a.py")
    assert am.paths.expand_glob(tmp_path, "nope/*.py") == []
    assert am.paths.expand_glob(tmp_path, "SRC/*.py") == []


def test_expand_glob_returns_files_only(am, tmp_path):
    touch(tmp_path, "src/sub/a.py")
    assert am.paths.expand_glob(tmp_path, "src/*") == []


# covers

def test_covers_literal_file(am):
    c = am.paths.covers
    assert c("a/b.py", "a/b.py")
    assert not c("a/b.py", "a/b.pyc")
    assert not c("a/b.py", "a/b.py/x")


def test_covers_dir_with_slash(am):
    c = am.paths.covers
    assert c("src/", "src/a.py")
    assert c("src/", "src/x/y/b.py")
    assert not c("src/", "srcx/a.py")
    assert not c("src/", "src")


def test_covers_dir_without_slash_needs_root(am, tmp_path):
    touch(tmp_path, "src/x/a.py")
    c = am.paths.covers
    assert not c("src", "src/x/a.py")
    assert c("src", "src/x/a.py", tmp_path)
    assert c("src", "src", tmp_path)
    assert not c("srcx", "src/x/a.py", tmp_path)
    assert not c("Src", "src/x/a.py", tmp_path)


def test_covers_glob(am):
    c = am.paths.covers
    assert c("src/**/*.py", "src/x/b.py")
    assert not c("src/*.py", "src/x/b.py")


# count_lines

@pytest.mark.parametrize(
    "data,expected",
    [
        (b"", 0),
        (b"a\r\nb\r\n", 2),
        (b"a\nb", 2),
        (b"a\nb\n", 2),
        (b"a\rb\r", 2),
        (b"\n", 1),
        (b"a\r\n\r\nb", 3),
        (b"\xef\xbb\xbfa\nb\n", 2),
        ("привет\nмир".encode("utf-8"), 2),
    ],
)
def test_count_lines_text(am, tmp_path, data, expected):
    p = touch(tmp_path, "f.txt", data)
    assert am.paths.count_lines(p) == expected


def test_count_lines_binary(am, tmp_path):
    assert am.paths.count_lines(touch(tmp_path, "a.bin", b"ab\x00cd")) is None
    assert am.paths.count_lines(touch(tmp_path, "b.txt", b"ab\xff\xfecd\n")) is None


def test_count_lines_nul_after_8k_but_invalid_utf8(am, tmp_path):
    p = touch(tmp_path, "c.bin", b"a" * 9000 + b"\xff")
    assert am.paths.count_lines(p) is None


def test_backslash_message_names_the_separator(am):
    assert "backslash" in am.paths.validate_rel_path("a\\b")
