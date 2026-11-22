# archmap

Status: private preview. No license is granted.

`archmap` is a stdlib-only Python 3.10+ tool. It guards a project's
`docs/architecture-map.json` (schema `archmap/1`) so the map cannot drift from the
code, and builds an offline, single-file HTML viewer of it.

## Install: one file

A project vendors a single file and needs nothing else (no pip, no dependencies).

1. Get `dist/archmap.py`: download the `archmap-single-file` artifact from a CI run,
   or build it locally with `python tools/build_single.py`.
2. Copy it to `tools/archmap/archmap.py` in your project and commit it.

The file is generated. Do not edit it; replace it with a newer build to upgrade.

### In the project's CI

```
python tools/archmap/archmap.py check
```

It exits 0 when the map is clean and 1 when the guard reports problems.

### Locally

```
python tools/archmap/archmap.py build
```

The viewer is written to `runtime/html-artifacts/architecture-map.html`
(override with `-o OUT`). `build` runs `check` first.

## Commands

```
archmap check [MAP] [--root DIR]            # validate the map against the schema and the repository
archmap build [MAP] [--root DIR] [-o OUT]   # check, then build the offline HTML viewer
archmap --version                           # print the version
```

`MAP` defaults to `<root>/docs/architecture-map.json`; `--root` defaults to the
current directory. With the package installed (`pip install -e .`) the same commands
run as `archmap ...` or `python -m archmap ...`.

## The `archmap/1` schema, briefly

Top level (all keys other than these are rejected):

- Required: `$schema` (must be `"archmap/1"`), `meta`, `nodes`, `edges`, `flows`.
- Optional: `reading_order`, `gotchas`, `unknowns`, `sections`.

`meta`:

- Required: `project`, `title`, `layers` (list of `{id, title?, hint?}`), `coverage`.
- Optional: `updated_at`, `purpose`, `stack`, `entrypoints`, `conventions`,
  `maintenance`, `source_url`, `secret_allow`.
- `coverage.core`: globs of the files the map must account for. Every core file has to
  appear in some node's `files`. `coverage.ignored`: `{glob, why}` entries that exempt
  files from that rule; `why` is required.
- `secret_allow`: `{match, why}` entries that silence a secret finding for one known
  harmless value. `match` is at least 6 characters; `why` is required.
- `source_url`: an `http://` or `https://` template with `{path}` and `{line}`
  placeholders, for example `https://host/org/repo/blob/main/{path}#L{line}`. The viewer
  uses it to link flow steps to source.

Content:

- `nodes[]`: `id`, `label`, `layer`, `summary` required; `kind`, `files`, `details`,
  `api`, `status`, `tech` optional. `files` may hold exact paths, directories (`dir/`)
  and globs.
- `edges[]`: `from`, `to` required; `label`, `kind` optional.
- `flows[]`: `id`, `title`, `steps` required (at least 2); each step needs `node` and
  `note`, and may carry `path`, `line`, `symbol`.
- `reading_order[]`, `gotchas[]`, `unknowns[]`, `sections{}`: free-form guidance shown
  in the viewer.

## Guard rules

`check` reports one line per problem, `code  where  message`. The codes:

| Group | Codes |
|---|---|
| Schema | `schema-missing`, `schema-unknown`, `section-missing`, `field-missing`, `field-invalid`, `field-unknown` |
| Identity and graph | `id-duplicate`, `layer-undeclared`, `edge-dangling`, `edge-self`, `node-orphan`, `step-node-missing`, `flow-too-short` |
| Paths | `path-invalid`, `path-missing`, `glob-empty`, `line-invalid` |
| Coverage | `coverage-core-empty`, `coverage-core-glob-empty`, `coverage-uncovered`, `coverage-ignore-no-why`, `coverage-ignore-unused` |
| Secrets | `secret-suspect`, `secret-allow-no-why`, `secret-allow-unused` |

## Development

```
pip install -e .[dev]
pytest -q                          # tests against the package
python tools/build_single.py       # writes dist/archmap.py (git-ignored)
ARCHMAP_IMPL=dist pytest -q        # the same tests against the single file
```
