---
id: F012
query_id: Q017+Q018
type: grep
intent: Look for documented provider-installation / extras guidance a lazy scheme must match
executed_at: 2026-09-29T16:00:00Z
parent_id: null
depth: 0
---

# F012 — README documents no extras; there is no setup.py to reconcile

## Summary

Grep for `pip install`, `extras`, `optional`, `[all]`, `[telegram]` in
`README.md` returns **zero matches**. Users are given no guidance on which
extra installs which provider, which is why a missing-SDK error (F008) is
currently unactionable. `setup.py` is not present as a dependency declaration
site — packaging is driven entirely by `pyproject.toml` (F007), with
`setuptools.build_meta` and a dynamic version from `notify/version.py`.

## Citations

- path: `README.md`
  lines: n/a
  symbol: install guidance
  excerpt: |
    (no matches for "pip install", "extras", "optional", "[all]", "[telegram]")

- path: `pyproject.toml`
  lines: 1-7, 136-137
  symbol: build system
  excerpt: |
    [build-system]
    requires = ["setuptools>=67.6.1", "Cython>=3.1.2", "wheel>=0.44.0"]
    build-backend = "setuptools.build_meta"
    ...
    [tool.setuptools.dynamic]
    version = { attr = "notify.version.__version__" }

## Notes

A `setup.py` does exist at the repo root for the Cython `build_ext` step
(`python setup.py build_ext --inplace` per CLAUDE.md), but it is not the
dependency-declaration surface.
