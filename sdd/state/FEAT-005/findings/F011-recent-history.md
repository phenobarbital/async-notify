---
id: F011
query_id: Q015+Q016
type: git_log
intent: Check recent activity on the factory and providers tree for in-flight refactors
executed_at: 2026-09-29T16:00:00Z
parent_id: null
depth: 0
---

# F011 — A lazy-loading trend is already established in this tree

## Summary

Nine commits in the last 120 days touch `notify/notify.py`, `notify/providers`
or `notify/__init__.py`. Two are directly on-theme: `64d3916` made uvloop an
optional dependency with an ImportError guard, and `b842186` (TASK-010 of the
templateparser-refactor feature) introduced the PEP 562 `__getattr__` that
defers `TemplateEnv`. This proposal continues an existing direction rather than
opening a new one.

## Citations

- path: `notify/notify.py`, `notify/providers`, `notify/__init__.py`
  lines: n/a
  symbol: git log --since="120 days ago"
  excerpt: |
    f2356d4 Merge branch 'dev' of github.com:phenobarbital/async-notify into dev
    64d3916 fix: make uvloop optional and build Windows wheels
    50deef1 Merge origin/dev into feat-002-templateparser-refactor
    b842186 feat(templateparser-refactor): TASK-010 — lazy TemplateEnv singleton via PEP 562
    1ea979a feat(jinja-string-notify): TASK-015 — three-way template= dispatch in ProviderBase._prepare_
    75e0eb0 Merge pull request #826 from phenobarbital/hotfix/msgraph-hostos-header
    e192410 fix(teams): sanitise msgraph-core HostOs telemetry header
    364be5f fix(ses): use async context manager to properly pair connect/close
    835755f fix(ses): call connect() before send() to initialize aiobotocore session

## Notes

`1ea979a` added the `is_template_source` call site in `ProviderBase._prepare_`
(F006) — i.e. the jinja2 edge in `base.py` is recent and was introduced for one
predicate call.
