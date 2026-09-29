---
id: F004
query_id: Q004
type: grep
intent: Find eager imports of concrete providers anywhere in the package (the premise under test)
executed_at: 2026-09-29T16:00:00Z
parent_id: null
depth: 0
---

# F004 — No module imports a concrete provider; only providers import their base

## Summary

21 matches for `from notify.providers…`. Every one is a provider module
importing *upward* into `base.py`, `mail.py` or `_mime_utils.py` — plus
`notify/__init__.py` and `notify/notify.py` importing `providers.base`. There is
**no** downward import (no module pulls `notify.providers.telegram` &c.), so no
eager provider fan-out exists anywhere in the package.

## Citations

- path: `notify/__init__.py`
  lines: 6
  symbol: import
  excerpt: |
    from .providers.base import ProviderType

- path: `notify/notify.py`
  lines: 7
  symbol: import
  excerpt: |
    from .providers.base import ProviderBase

- path: `notify/providers/telegram/Telegram.py`
  lines: 28
  symbol: import
  excerpt: |
    from notify.providers.base import ProviderIM, ProviderType

- path: `notify/providers/mail.py`
  lines: 12
  symbol: import
  excerpt: |
    from notify.providers import _mime_utils as _mu

## Notes

Pattern is uniform across all 17 providers: `base.py` for IM/SMS/push,
`mail.py` for the six email providers (aws, email, gmail, office365, outlook,
sendgrid, ses).
