---
id: F003
query_id: Q003
type: glob
intent: List every provider package to size the eager-import surface
executed_at: 2026-09-29T16:00:00Z
parent_id: null
depth: 0
---

# F003 — 17 provider packages; none reachable from `import notify`

## Summary

`notify/providers/` holds 17 provider packages plus four shared modules
(`base.py`, `mail.py`, `message.py`, `_mime_utils.py`) and an empty
`__init__.py`. Only `base.py` (and transitively `message.py`) is reachable from
`import notify`; `mail.py` and every provider package are reached only through
`LoadProvider`.

## Citations

- path: `notify/providers/`
  lines: n/a
  symbol: directory listing
  excerpt: |
    aws/ dialpad/ dummy/ email/ gmail/ office365/ onesignal/ outlook/
    sendgrid/ ses/ slack/ smtp/ teams/ telegram/ twilio/ xmpp/ zoom/
    __init__.py  _mime_utils.py  base.py  mail.py  message.py

## Notes

18 `__init__.py` files under `notify/providers/` (17 providers + the package
itself).
