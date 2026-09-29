---
id: F009
query_id: Q012
type: grep
intent: Check how the notify server / wrapper resolves providers, since it may bypass the factory
executed_at: 2026-09-29T16:00:00Z
parent_id: null
depth: 0
---

# F009 — The server also goes through the lazy factory; no eager fan-out

## Summary

`notify/server/wrapper.py` instantiates providers via `Notify(self._provider, **kwargs)`
— the same lazy path. `notify/server/queue.py` has its own `importlib.import_module`
for queue backends, also lazy and guarded by `except ImportError`. No module in
`notify/server/` enumerates or preloads providers. `notify/__main__.py` (the
`notify` console script) imports only `notify.server`, `notify.conf` and
`notify.utils.uv`.

## Citations

- path: `notify/server/wrapper.py`
  lines: 71, 83
  symbol: provider instantiation
  excerpt: |
            notify: coro = Notify(self._provider, **self.kwargs)

- path: `notify/server/queue.py`
  lines: 65-67
  symbol: queue backend loader
  excerpt: |
            module = importlib.import_module(classpath, package=bkname)
        except ImportError as ex:

- path: `notify/__main__.py`
  lines: 4-9
  symbol: module imports
  excerpt: |
    from notify.server import NotifyWorker
    from notify.conf import (
        NOTIFY_DEFAULT_HOST,
        NOTIFY_DEFAULT_PORT
    )
    from notify.utils.uv import install_uvloop

## Notes

`NOTIFY_USE_DISCOVERY` exists as a config flag in `notify/conf.py` (line 20) but
no provider-discovery walk was found in the package.
