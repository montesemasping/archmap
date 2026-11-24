"""The agent skill and the plugin manifests stay in step with the tool."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKILL = ROOT / "skills" / "architecture-map" / "SKILL.md"
PLUGIN = ROOT / ".claude-plugin" / "plugin.json"
MARKET = ROOT / ".claude-plugin" / "marketplace.json"

# Problem codes that come from the loader, not from the guard.
LOADER_CODES = {"json-invalid"}
CODE_RE = re.compile(
    r"`((?:schema|section|field|id|layer|edge|node|step|flow|path|glob|line|coverage|secret|json)-[a-z-]+)`"
)


def _frontmatter(text):
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert m, "SKILL.md must start with a YAML frontmatter block"
    fields = {}
    for line in m.group(1).splitlines():
        key, _, value = line.partition(": ")
        fields[key] = value
    return fields


def test_skill_frontmatter():
    fields = _frontmatter(SKILL.read_text(encoding="utf-8"))
    assert set(fields) == {"name", "description"}
    assert fields["name"] == SKILL.parent.name
    assert fields["description"].startswith("Use ")
    assert len(fields["description"]) <= 1024


def test_skill_names_only_real_codes(am):
    text = SKILL.read_text(encoding="utf-8")
    named = set(CODE_RE.findall(text))
    assert named, "the skill should name the guard codes it explains"
    unknown = named - set(am.guard.GUARD_CODES) - LOADER_CODES
    assert not unknown, f"SKILL.md names codes archmap does not have: {sorted(unknown)}"


def test_skill_points_at_files_that_exist():
    text = SKILL.read_text(encoding="utf-8")
    for rel in ("README.md", "CHANGELOG.md", "tools/build_single.py",
                "tests/fixtures/bakery/docs/architecture-map.json", ".claude-plugin/plugin.json"):
        assert f"`{rel}`" in text, rel
        assert (ROOT / rel).is_file(), rel


def test_skill_has_no_machine_paths():
    text = SKILL.read_text(encoding="utf-8")
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
    assert (ROOT / "skills" / "architecture-map" / "SKILL.md").is_file()
