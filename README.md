# archmap

Status: private preview. No license is granted.

`archmap` is a stdlib-only Python 3.10+ CLI. It guards a project's
`docs/architecture-map.json` (schema `archmap/1`) and builds an offline,
single-file HTML viewer of it.

## Commands

```
archmap check [path]    # validate the map against the schema and the repository
archmap render [path]   # build the offline HTML viewer
archmap version         # print the version
```

## Development

```
pip install -e .[dev]
pytest -q
```
