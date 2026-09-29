---
id: F005
query_id: Q014
type: read
intent: Measure the real cost — which imports dominate `import notify` wall time today
executed_at: 2026-09-29T16:00:00Z
parent_id: null
depth: 0
---

# F005 — `import notify` costs ~192 ms; ~86% is navconfig + datamodel + jinja2

## Summary

Measured on this machine, python 3.11, warm filesystem cache. `import notify`
takes **190-194 ms** across 5 runs. Attribution by pre-loading each third-party
tree and re-measuring the marginal cost of `import notify`:

| preloaded | `import notify` marginal | attributable to preloaded tree |
|---|---:|---:|
| nothing | 192 ms | — |
| `navconfig` | 70.4 ms | **~122 ms (63%)** |
| `datamodel` + `jinja2` | 122.8 ms | **~69 ms (36%)** |
| `navconfig`+`datamodel`+`jinja2` | 35.1 ms | ~157 ms (82%) |

Isolated costs: navconfig 123.2 ms · datamodel 54.1 ms · jinja2 27.8 ms ·
asyncio 24.0 ms. The stdlib set that `base.py`/`notify.py` need
(asyncio, abc, enum, functools, importlib, threading, pathlib,
concurrent.futures) costs 27.0 ms on its own — a hard floor.

`python -X importtime` confirms the shape: `notify.providers.base` has a
cumulative 214 ms but only **21.1 ms of self time**; the rest is its children.

## Citations

- path: `notify/providers/base.py`
  lines: 5-19
  symbol: module imports
  excerpt: |
    import asyncio
    from abc import ABC, abstractmethod
    from concurrent.futures import ThreadPoolExecutor
    from navconfig import DEBUG
    from navconfig.logging import logging
    from notify.types import SafeDict
    from notify.exceptions import ProviderError
    from notify.models import Actor
    from notify.templates import is_template_source
    from .message import ThreadMessage

- path: `notify/templates.py`
  lines: 11-25
  symbol: module imports
  excerpt: |
    from jinja2 import (
        BaseLoader, ChoiceLoader, DictLoader, Environment,
        FileSystemBytecodeCache, FileSystemLoader, StrictUndefined,
        Template, TemplateError, TemplateNotFound,
        TemplateSyntaxError, Undefined,
    )
    from navconfig import config as nav_config

- path: `notify/conf.py`
  lines: 1-10
  symbol: module body
  excerpt: |
    from pathlib import Path
    from navconfig import BASE_DIR, config

    if not (template_dir := config.get('TEMPLATE_DIR')):
        TEMPLATE_DIR = BASE_DIR.joinpath("templates")
    else:
        TEMPLATE_DIR = Path(template_dir).resolve()

## Notes

`-X importtime` sub-trees inside navconfig: `navconfig.kardex` 103.6 ms cum,
of which `navconfig.readers.vault` 65.4 ms (→ hvac → requests → urllib3 33.5 ms)
and `navconfig.readers.redis` 18.8 ms (→ redis.asyncio). `datamodel` pulls
`asyncpg` (10.9 ms). None of this is provider code.
