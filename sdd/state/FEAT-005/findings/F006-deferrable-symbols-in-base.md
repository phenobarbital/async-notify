---
id: F006
query_id: Q009
type: read
intent: Read ProviderBase to learn the contract a lazy loader must still satisfy
executed_at: 2026-09-29T16:00:00Z
parent_id: null
depth: 0
---

# F006 — base.py pulls datamodel + jinja2 for one annotation and one pure predicate

## Summary

`notify/providers/base.py` imports `Actor` (→ `notify.models` → `datamodel` →
`asyncpg`) and `is_template_source` (→ `notify.templates` → `jinja2`). Every
`Actor` reference in the file is a **type annotation only** — no runtime use —
so it is removable via `TYPE_CHECKING`. `is_template_source` is a pure string
predicate with no jinja2 dependency of its own; it merely lives in a module that
imports jinja2 at top level, and it is called once, inside `_prepare_`. Only
`DEBUG` (navconfig, line 64) is a genuine runtime module-level need.

## Citations

- path: `notify/providers/base.py`
  lines: 12-19
  symbol: module imports
  excerpt: |
    from navconfig import DEBUG
    from navconfig.logging import logging
    from notify.types import SafeDict
    from notify.exceptions import ProviderError
    from notify.models import Actor
    from notify.templates import is_template_source

- path: `notify/providers/base.py`
  lines: 64
  symbol: `ProviderBase.__init__`
  excerpt: |
            self._debug = DEBUG

- path: `notify/providers/base.py`
  lines: 119, 169, 189, 210, 228, 265
  symbol: `Actor` usages
  excerpt: |
    recipient: Actor = None,                      # 119  (annotation)
    self, to: Actor = None, message: str = None,  # 169  (annotation)
    self, to: Actor, message: Union[str, Any],    # 210  (annotation)
    recipient: list[Actor] = None,                # 265  (annotation)

- path: `notify/providers/base.py`
  lines: 155
  symbol: `_prepare_`
  excerpt: |
                    use_source = is_template_source(template)

- path: `notify/templates.py`
  lines: 95-107
  symbol: `is_template_source`
  excerpt: |
    def is_template_source(value: str) -> bool:
        """Decide whether *value* is Jinja2 source text rather than a filename.

        Conservative by design: returns ``True`` only when *value* carries a
        signal that a template filename cannot carry — a Jinja2 delimiter
        (``{{``, ``{%``, ``{#``) or a line break.

## Notes

Precedent already in-tree: `notify/notify.py` defers `TemplateEnv` construction
via PEP 562 `__getattr__` (commit b842186, TASK-010 of the templateparser
refactor). The same technique applies at the package and module level.
