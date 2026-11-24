"""The agent skill and the plugin manifests stay in step with the tool."""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "architecture-map" / "SKILL.md"
PLUGIN = ROOT / ".claude-plugin" / "plugin.json"
MARKET = ROOT / ".claude-plugin" / "marketplace.json"

# Problem codes that the loader emits, not the guard. Each is proven below.
LOADER_CODES = {"json-invalid"}
# Backticked kebab-case words in SKILL.md that are not problem codes. Each must still occur.
NOT_CODES: set = set()
# Backticked paths that start like this belong to the archmap repository, not to the
# target project, and must exist here.
REPO_PATH_RE = re.compile(r"`((?:README|CHANGELOG)\.md|(?:tests|skills|src|tools/build_single)[^`\s]*|\.claude-plugin/[^`\s]+)`")


def _text():
    return SKILL.read_text(encoding="utf-8")


def _frontmatter(text):
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert m, "SKILL.md must start with a YAML frontmatter block"
    fields = {}
    for line in m.group(1).splitlines():
        key, _, value = line.partition(": ")
        fields[key] = value
    return fields


def test_skill_frontmatter():
    fields = _frontmatter(_text())
    assert set(fields) == {"name", "description"}
    assert fields["name"] == SKILL.parent.name
    assert fields["description"].startswith("Use ")
    assert len(fields["description"]) <= 1024


def _named_codes(text):
    body = text.split("\n---\n", 1)[1]  # the description lists codes without backticks
    kebab = set(re.findall(r"`([a-z]+(?:-[a-z]+)+)`", body))
    bracketed = set(re.findall(r"\[([a-z]+(?:-[a-z]+)+)\]", body))
    return kebab | bracketed


def test_skill_names_only_real_codes(am):
    text = _text()
    named = _named_codes(text)
    assert named, "the skill should name the guard codes it explains"
    unknown = named - set(am.guard.GUARD_CODES) - LOADER_CODES - NOT_CODES
    assert not unknown, f"SKILL.md names codes archmap does not have: {sorted(unknown)}"
    assert NOT_CODES <= named, f"stale NOT_CODES entries: {sorted(NOT_CODES - named)}"


def test_description_names_only_real_codes(am):
    desc = _frontmatter(_text())["description"]
    m = re.search(r"when archmap check fails \(([^)]*)\)", desc)
    assert m, "the description should list the codes that trigger the skill"
    codes = {c.strip() for c in m.group(1).split(",")}
    assert codes <= set(am.guard.GUARD_CODES), sorted(codes - set(am.guard.GUARD_CODES))


@pytest.mark.parametrize("code", sorted(LOADER_CODES))
def test_loader_codes_are_real(am, tmp_path, code):
    bad = tmp_path / "map.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(am.MapLoadError) as err:
        am.load_map(bad)
    assert err.value.problem.code == code


def _table_paths(text):
    """Paths in the 'Where' column of the table that lists the repository's files."""
    section = text.split("In that repository:", 1)[1].split("\n## ", 1)[0]
    rows = [line for line in section.splitlines() if line.startswith("| ") and not line.startswith("| What")]
    paths = []
    for row in rows:
        cells = [c.strip() for c in row.strip("|").split("|")]
        if set(cells[-1]) <= {"-"}:
            continue
        found = re.findall(r"`([^`]+)`", cells[-1])
        assert len(found) == 1, f"one path per 'Where' cell: {row}"
        paths.append(found[0])
    return paths


def test_skill_table_points_at_files_that_exist():
    paths = _table_paths(_text())
    assert paths
    for rel in paths:
        assert (ROOT / rel).is_file(), rel


def test_skill_repo_references_exist():
    # Globs and placeholders (`src/**/*.ts`, `<archmap>`) are examples, not references.
    refs = {r for r in REPO_PATH_RE.findall(_text()) if "*" not in r and "<" not in r}
    assert ".claude-plugin/plugin.json" in refs
    for rel in refs:
        assert (ROOT / rel).exists(), rel


def test_skill_has_no_machine_paths():
    text = _text()
    assert not re.search(r"\b[A-Za-z]:[\\/]", text), "drive-letter path in SKILL.md"
    assert "/home/" not in text and "/Users/" not in text


def test_plugin_manifests_match_the_version(am):
    plugin = json.loads(PLUGIN.read_text(encoding="utf-8"))
    market = json.loads(MARKET.read_text(encoding="utf-8"))
    assert plugin["name"] == "archmap"
    assert plugin["version"] == am.__version__
    assert [p["name"] for p in market["plugins"]] == [plugin["name"]]
    assert market["plugins"][0]["source"] == "./"
    # Claude Code discovers skills in the plugin's default `skills/` directory.
    assert SKILL.is_file()
