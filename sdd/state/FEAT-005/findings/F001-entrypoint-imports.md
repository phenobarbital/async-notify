---
id: F001
query_id: Q001
type: read
intent: Read the package entrypoint to see what notify/__init__.py imports at import time
executed_at: 2026-09-29T16:00:00Z
parent_id: null
depth: 0
---

# F001 — notify/__init__.py imports no concrete provider

## Summary

The package entrypoint imports exactly three things: `ProviderType` from
`notify.providers.base`, the `Notify` factory, and `install_uvloop`. It does
**not** import any concrete provider (telegram, slack, ses, …). The premise
"async-notify carga al arranque todos los providers" is therefore **not true at
the package-root level**. The startup cost comes from the transitive closure of
`notify.providers.base`, not from provider modules.

## Citations

- path: `notify/__init__.py`
  lines: 6-16
  symbol: module body
  excerpt: |
    from .providers.base import ProviderType
    from .notify import Notify
    from .utils.uv import install_uvloop

    install_uvloop()

    __all__ = (
        "Notify",
        "ProviderType",
    )

- path: `notify/providers/__init__.py`
  lines: 1-4
  symbol: module body
  excerpt: |
    """Providers.

    Directory for all Notification Providers.
    """

## Notes

`notify/providers/__init__.py` is a docstring only — no registry, no
re-exports, no `__all__`. There is nothing here to make lazy.
