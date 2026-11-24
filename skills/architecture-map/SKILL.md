---
name: architecture-map
description: Use before exploring an unfamiliar repository (read docs/architecture-map.json first if it exists), when a change adds, removes, renames or moves modules, routes, services or jobs (update the map in the same change), when archmap check fails (coverage-uncovered, path-missing, glob-empty, secret-suspect), and when asked to connect archmap or create an architecture map with a guard for a project.
---

# Architecture Map + archmap guard

A prose `ARCHITECTURE.md` goes stale silently after the first refactor. A machine-readable map with a guard lives as long as the code, because drifting from the code fails the checks. The map is the entry point into a repository for agents and humans: read it before walking directories.

The guard is **archmap**: one stdlib-only Python 3.10+ file that a project vendors as `tools/archmap/archmap.py`. It validates `docs/architecture-map.json` (schema `archmap/1`) against the repository and builds an offline HTML viewer.

This skill ships inside the archmap repository, two directories above this file (`skills/architecture-map/SKILL.md`). In that repository:

| What | Where |
|---|---|
| Schema, commands, guard rules (reference) | `README.md` |
| Small complete example map | `tests/fixtures/bakery/docs/architecture-map.json` |
| Single-file build | `tools/build_single.py`, writes `dist/archmap.py` |
| Release notes | `CHANGELOG.md` |

If only this file was installed, without the repository around it, clone the repository named in `.claude-plugin/plugin.json` (`repository`) or ask the user where archmap lives.

## 1. Reading an existing map

If `docs/architecture-map.json` exists, start there, not with `ls -R`:
1. `meta`: `purpose`, `stack`, `layers`, `entrypoints`, `conventions`, `maintenance`.
2. `reading_order`: what to read next, in order, each with a `why`.
3. `gotchas` and `unknowns`: things that break silently, and what nobody has verified yet.
4. `flows`: end-to-end scenarios; each step names a `node` and usually a `path`, `line` or `symbol`. Follow the flow that matches your task.
5. `nodes[].files`: which files implement a component; `edges`: who calls whom. `sections`: project prose (product context, roadmap).

Trust the file references (the guard keeps them alive). Prose can still be wrong: verify anything your change depends on.

To look at it as a diagram: `python tools/archmap/archmap.py build`, then open `runtime/html-artifacts/architecture-map.html`.

## 2. Keeping it current

If your change adds, removes, renames or moves a module under the coverage core, or adds a subsystem, route group, job, integration or entrypoint, update the map **in the same change**:
- a new module goes into the `files` of the node that owns it;
- a new subsystem gets a node and at least one edge (an edgeless node is `node-orphan`);
- a changed flow gets its step `path`/`line`/`symbol` fixed;
- remove `gotchas` and `unknowns` that are no longer true.

Then run `python tools/archmap/archmap.py check`. It must print `no problems` (exit 0). A red guard means the map and the code disagree: fix the map or the code. Never weaken the guard: do not widen globs to swallow files, do not add `coverage.ignored` or `secret_allow` entries just to go green. Both need a real `why`.

| Code | Usually means |
|---|---|
| `coverage-uncovered` | a core file is in no node's `files`: add it to its owner |
| `path-missing`, `glob-empty` | a file was moved or deleted: fix the reference |
| `node-orphan`, `edge-dangling` | a node has no edges, or an edge names a node that does not exist |
| `coverage-ignore-unused`, `secret-allow-unused` | an exemption no longer matches anything: delete it |
| `secret-suspect` | a string looks like a credential: remove it; `build` refuses to write HTML until then |
| `field-unknown`, `schema-unknown` | the schema is closed: only `archmap/1` fields are allowed (see `README.md`) |

## 3. Connecting archmap to a project

Do it as a normal task: own branch, review by the project's rules, merge by its owner's rules. One working session for a mid-size repo. Not worth it for a repo readable in an hour.

### 3.1 Find the live branch first

The checked-out branch is not necessarily where work happens. Before branching, `git fetch` and compare the candidates: `git log -1 --format='%ci %d' origin/<branch>` for `main`, `master`, `develop`, `dev`, `staging`. Read the project's `AGENTS.md`/`CLAUDE.md` for the working branch. Branch from the live line; if it is unclear, ask. A map built on a stale branch is wrong on day one.

### 3.2 Vendor the guard

Build the single file from a release tag of archmap:
```
git -C <archmap> checkout v<X.Y.Z>        # or clone it with --branch v<X.Y.Z> --depth 1
python <archmap>/tools/build_single.py    # writes <archmap>/dist/archmap.py
```
Copy `dist/archmap.py` to `tools/archmap/archmap.py` in the project and commit it unchanged. `python tools/archmap/archmap.py --version` prints the version. The build is deterministic: rebuilding the same tag gives the same bytes, so a vendored copy can be verified by rebuilding and comparing hashes. Upgrading means replacing the file with a newer build. Never edit it; report an archmap bug upstream and work around it in the project.

### 3.3 Write `docs/architecture-map.json`

Start from the bakery example and the `README.md` schema. Required: `$schema: "archmap/1"`, `meta` (`project`, `title`, `layers`, `coverage`), `nodes`, `edges`, `flows`.

- **Coverage core** (`meta.coverage.core`): globs of the code the map must account for, for example `app/**/*.py` or `src/**/*.ts`. Exempt files only through `coverage.ignored` entries `{glob, why}` (typical: `**/__init__.py`, "package markers").
- **Node `files`**: exact paths, `dir/`, or narrow globs. A whole-tree entry (`*`, `**`, `**/*.py`) is rejected as `path-invalid`. Prefer exact paths: a new module then shows up as `coverage-uncovered` instead of being silently swallowed.
- **Flows**: the 3-6 paths that matter (sign-up, the main user journey, payments, refunds, background jobs). At least two steps each, every step with a `note`.
- **Beyond structure**, put in what the code does not show: product context (`sections`), reasons for decisions, `gotchas` from the project's agent instructions and notes, `unknowns`. Prose in the project's working language, identifiers as they are.
- **No secrets.** No tokens, keys, real passwords or connection strings, not even as examples.

Iterate with `python tools/archmap/archmap.py check` until `no problems`. Then `build` and actually open the HTML.

### 3.4 Wire the check into what actually runs

Find out what runs on every change before choosing:
- **CI exists**: add a step `python tools/archmap/archmap.py check` with only the interpreter set up. No path filter: the map drifts exactly in changes that do not think about it.
- **No CI**: add a test to the suite that runs the check as a subprocess. It needs two assertions: the map passes (exit 0, `no problems`), and a mutation fails (remove one core file from its node's `files` in a temporary copy, pass that copy as `MAP` with `--root` at the repository, expect exit 1 and `[coverage-uncovered]`). Without the second, a guard that checks nothing would stay green.
- Run the suite the way the project runs it. Shared fixtures may pull in a database, and a shared test database can sit on another branch's migration revision. Use a throwaway database rather than migrating a shared one.
- If the project builds container images and excludes tests from them, exclude `tools/` and `docs/architecture-map.json` too.

### 3.5 Tell agents about it

Add a section near the top of the project's `AGENTS.md` (and `CLAUDE.md` if it holds the rules):

> **Architecture Map.** The map lives in `docs/architecture-map.json` (schema `archmap/1`). Read it first when you need to find where something lives. The guard `tools/archmap/archmap.py` is a vendored build of archmap vX.Y.Z: do not edit it. Whenever the structure of `<core>` changes, update the map in the same change and run `python tools/archmap/archmap.py check`; it must print `no problems`. It also runs in `<CI step or test>`. Viewer: `python tools/archmap/archmap.py build`.

### 3.6 Finish

- The project's review rules apply to the diff: map, vendored file, test or CI step, agent instructions.
- Do not push or create remote branches unless the project's rules or its owner allow it.
- Say in the summary which branch the work landed on.

## Common mistakes

| Mistake | Instead |
|---|---|
| Branching from whatever is checked out | 3.1: find the live branch |
| `files: ["app/**/*.py"]` on one big node | exact paths per owning node; broad globs belong in `coverage.core` |
| Editing `tools/archmap/archmap.py` to silence a rule | fix the map; report a real archmap bug upstream |
| Only a "map passes" test | add the mutation assertion |
| Green check, nobody opened the HTML | `build` and look: wrong layers and empty flows show at a glance |
| Map lists modules but says nothing the code does not | add purpose, flows, gotchas, unknowns |

The guard catches dead references and uncovered files, not wrong conclusions. Facts that span repositories (a worker defined in deployment config, an environment default overridden elsewhere) still need checking by hand.
