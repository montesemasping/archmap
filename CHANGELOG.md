# Changelog

## Unreleased

- Agent skill `skills/architecture-map/SKILL.md`: reading a map, keeping it current,
  connecting archmap to a project. The repository is also a Claude Code plugin
  (`.claude-plugin/plugin.json`, `marketplace.json`).

## 0.1.0

- `check`: guards `docs/architecture-map.json` (schema `archmap/1`) against the code:
  schema, ids and edges, existing paths and line numbers, core coverage, and secrets.
- `build`: renders the map into an offline, self-contained HTML file.
- The viewer: layered graph, flows, node details, search, and links to source through
  `meta.source_url`.
- Single-file distribution: `python tools/build_single.py` writes `dist/archmap.py`, a
  stdlib-only file a project can vendor as `tools/archmap/archmap.py`. CI builds it,
  runs the full test suite against it, and uploads it as an artifact.
