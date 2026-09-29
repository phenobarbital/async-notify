# TASK-35: Defer datamodel and jinja2 off the `import notify` startup path

**Feature**: FEAT-005 — Actionable optional-dependency diagnostics and a slim core install
**Spec**: `sdd/specs/lazy-import-providers.spec.md`
**Status**: pending
**Priority**: medium
**Estimated effort**: M (2-4h)
**Depends-on**: TASK-34
**Assigned-to**: unassigned

---

## Context

Implements **spec §3 Module 3**, serving goal **G6** (kept in scope by the user's
decision at `/sdd-task` time, resolving spec §8's open question).

`import notify` costs ~196-203 ms. navconfig (~124 ms) stays — spec §1 scopes it
out explicitly — but two of `notify/providers/base.py`'s three heavy edges are
nearly free to cut: `Actor` is used **only** in annotations, and
`is_template_source` is a pure string predicate that merely happens to live in a
module that imports jinja2. Marginal saving, measured with navconfig preloaded:
datamodel ≈ 21 ms, jinja2 ≈ 12 ms, both ≈ **34 ms**.

Depends on TASK-34 because both tasks edit `notify/notify.py`; sequencing them
avoids a conflicting rewrite of the same file.

---

## Scope

- Create `notify/utils/templates.py` holding `JINJA_MARKERS` and
  `is_template_source`, importing **nothing** heavy.
- Re-export both from `notify/templates.py` for backward compatibility, silently.
- Switch `notify/providers/base.py` to `TYPE_CHECKING` for `Actor` and to the new
  module for `is_template_source`.
- **Also switch `notify/providers/message.py` to `TYPE_CHECKING` for `Actor`** —
  see "Discovered gap" below; without it G6 cannot pass.
- Move `from .conf import TEMPLATE_DIR` and `from .templates import TemplateParser`
  inside `notify/notify.py`'s `__getattr__`.

**NOT in scope**: deferring navconfig or making `notify/conf.py` lazy (spec §1
Non-Goals, user decision U2). `LoadProvider` / `PROVIDER_EXTRAS` (TASK-34).
The new test files (TASK-39). Do **not** change `is_template_source`'s behaviour
— it moves verbatim.

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `notify/utils/templates.py` | CREATE | jinja2-free home for `JINJA_MARKERS` + `is_template_source` |
| `notify/templates.py` | MODIFY | Delete the two definitions; re-export from the new module |
| `notify/providers/base.py` | MODIFY | `from __future__ import annotations`; `TYPE_CHECKING` `Actor`; new `is_template_source` path |
| `notify/providers/message.py` | MODIFY | `from __future__ import annotations`; `TYPE_CHECKING` `Actor` |
| `notify/notify.py` | MODIFY | `from __future__ import annotations`; move two imports into `__getattr__` |

---

## Codebase Contract (Anti-Hallucination)

> Verified against `dev` @ `d72fe6e` on 2026-09-29.

### Verified Imports

```python
from notify.templates import is_template_source, JINJA_MARKERS  # verified: notify/templates.py:89,95
from notify.models import Actor                                 # verified: notify/providers/base.py:18
from notify.utils.functions import cPrint, Msg                  # verified: notify/utils/__init__.py:1
```

### Existing Signatures to Use

```python
# notify/templates.py
from jinja2 import (BaseLoader, ChoiceLoader, ..., Undefined)   # line 11  (why this module is heavy)
jinja_config = {...}                                            # lines 82-85
JINJA_MARKERS: tuple[str, ...] = ("{{", "{%", "{#")             # line 89  (preceded by a `#:` comment, line 88)
DEFAULT_STRING_CACHE_SIZE: int = 128                            # line 92  (STAYS — not part of the move)
def is_template_source(value: str) -> bool:                     # lines 95-114
class TemplateParser:                                           # line 117

# notify/providers/base.py
from navconfig import DEBUG                                     # line 12  (runtime use line 64 — NOT deferrable)
from notify.types import SafeDict                               # line 14  (Cython — cheap)
from notify.exceptions import ProviderError                     # lines 15-17 (Cython — cheap)
from notify.models import Actor                                 # line 18  (annotations only — DEFER)
from notify.templates import is_template_source                 # line 19  (DEFER via move)
from .message import ThreadMessage                              # line 20
class ProviderBase(ABC):                                        # line 31
    use_source = is_template_source(template)                   # line 155 (sole runtime call site)
# Actor referenced at lines 119, 169, 189, 210, 228, 265 — every one an annotation
# Also a docstring mention at line 135 (":func:`notify.templates.is_template_source`")

# notify/providers/message.py
from notify.models import Actor                                 # line 6   (annotations only — DEFER)
class ThreadMessage(threading.Thread):                          # line 9
    def __init__(self, fn, callback, queue, rcpt: Actor, ...)   # line 15  (sole Actor reference)

# notify/notify.py  (line numbers AFTER TASK-34 lands — re-verify before editing)
from .conf import TEMPLATE_DIR                                  # was line 5
from .templates import TemplateParser                           # was line 8
_TEMPLATE_ENV: TemplateParser | None = None                     # was line 15  <- SEE "annotation trap"
def __getattr__(name: str):                                     # was line 89 — sole consumer of both
def __dir__() -> list[str]:                                     # was line 119

# notify/utils/__init__.py — imports .functions only
# notify/utils/functions.py — ZERO imports (pure stdlib). Must STAY that way.
```

### Measured baseline (reproduce before you start)

```
$ python -c "import sys, notify; print('jinja2' in sys.modules, 'datamodel' in sys.modules)"
True True        # <- today. Both must read False when this task is done.
```

### Does NOT Exist

- ~~`notify.utils.templates`~~ — **this task creates it**.
- ~~a jinja2 dependency inside `is_template_source`~~ — it is a pure string
  predicate over `JINJA_MARKERS`, `\n` and `\r`. It moves verbatim.
- ~~`typing.get_type_hints` callers in this repository~~ — zero occurrences
  (repo-wide grep excluding `.venv`). This is why the `Actor` deferral is safe here.
- ~~a runtime use of `Actor` in `base.py` or `message.py`~~ — all 7 references
  across both files are annotations.
- ~~`DEFAULT_STRING_CACHE_SIZE` belonging in the new module~~ — it stays in
  `notify/templates.py`; only `JINJA_MARKERS` and `is_template_source` move.

---

## Implementation Notes

### Discovered gap — the spec's M3 file list is incomplete

Spec §3 M3 lists only `base.py`, but `base.py:20` imports `.message`, and
`notify/providers/message.py:6` imports `Actor` from `notify.models` too. Verified:
its **only** reference is the annotation `rcpt: Actor` at line 15. If that import
is left eager, `datamodel` stays in `sys.modules` after `import notify` and
**AC-G6 fails no matter what you do to `base.py`**. Hence `message.py` is in scope
here. Apply exactly the same `from __future__ import annotations` + `TYPE_CHECKING`
treatment.

### The annotation trap in `notify/notify.py`

`_TEMPLATE_ENV: TemplateParser | None = None` is a **module-level annotated
assignment**. Moving `from .templates import TemplateParser` into `__getattr__`
turns that line into a `NameError` at import time — unless
`from __future__ import annotations` (PEP 563) is added, which makes every
annotation in the module a string and leaves it unevaluated. Add the `__future__`
import **first**, or the module stops importing entirely.

### The re-export must be silent — but not for the reason the spec gives

Spec §3 M3 and §7 say `pyproject.toml`'s `filterwarnings = ["error", ...]` makes a
`DeprecationWarning` fail CI. **That enforcement does not exist.** `pytest.ini` is
present at the repo root, and pytest uses exactly one config file: it takes
`pytest.ini` and ignores `[tool.pytest.ini_options]` entirely — pytest says so out
loud on every run:

```
configfile: pytest.ini (WARNING: ignoring pytest config in pyproject.toml!)
```

The effective setting is `pytest.ini`'s `filterwarnings = ignore::DeprecationWarning`
— the opposite. So `--strict-markers`, `--strict-config` and the `error` filter are
all inert today.

The requirement still stands on its own merits: the re-export is a supported public
path, not a deprecated one, so it must emit **no** warning. Do not add a module
`__getattr__` that warns, and do not add a `warnings.warn` call. A plain
`from notify.utils.templates import ...` at the top of `notify/templates.py` is what
is wanted. Just do not rely on the test suite to catch it for you — assert it
explicitly (TASK-39 does, with `warnings.catch_warnings(record=True)`).

### Key Constraints

- `notify/utils/templates.py` **MUST NOT** import jinja2, datamodel or navconfig,
  directly or transitively. It is reached via `notify/utils/__init__.py`, which
  imports `notify.utils.functions` — a zero-import, pure-stdlib module that must
  stay that way or the whole deferral is undone.
- Public import paths are unchanged: `from notify.templates import
  is_template_source, JINJA_MARKERS` must keep working.
- **Accepted, documented behaviour change**: `typing.get_type_hints()` on
  `ProviderBase` / `ThreadMessage` methods will no longer resolve `Actor`. PEP 563
  prevents the import-time failure but `get_type_hints` evaluates the string
  against module globals, and a module `__getattr__` does not rescue it. The repo
  has zero callers; TASK-36 records it in `CHANGES.rst` and TASK-39 pins it.
- Google-style docstrings, strict type hints, `black --line-length 120`.

---

## Implementation Blueprint

### Steps (in order)

1. Create `notify/utils/templates.py` — *why*: everything else re-points at it, so
   it must exist first.
2. Strip the two definitions out of `notify/templates.py` and re-export them —
   *why*: two definitions of `is_template_source` would silently diverge.
3. Re-point `base.py`, adding `from __future__ import annotations` — *why*: the
   `Actor` annotations at six sites only survive as strings.
4. Re-point `message.py` the same way — *why*: the discovered gap above; without
   it `datamodel` stays resident and G6 cannot pass.
5. Add `from __future__ import annotations` to `notify/notify.py`, **then** move
   the two imports into `__getattr__` — *why*: the annotation trap above.
6. Rebuild Cython (`python setup.py build_ext --inplace`) and re-run the baseline
   probe — *why*: spec §7 says a measurement against stale `.so` files is invalid.

### `notify/utils/templates.py` (CREATE)

```python
"""Lightweight template helpers.

Deliberately free of jinja2, datamodel and navconfig imports: this module sits
on the ``import notify`` startup path via :mod:`notify.providers.base`, and
pulling any of those three back in undoes FEAT-005's G6 deferral.
"""
from __future__ import annotations

#: Jinja2 delimiters that can never appear in a template *filename*.
JINJA_MARKERS: tuple[str, ...] = ("{{", "{%", "{#")


def is_template_source(value: str) -> bool:
    """Decide whether *value* is Jinja2 source text rather than a filename.

    Conservative by design: returns ``True`` only when *value* carries a
    signal that a template filename cannot carry — a Jinja2 delimiter
    (``{{``, ``{%``, ``{#``) or a line break. Anything else is treated as a
    filename, which preserves 1.5.7 behaviour for every existing caller.

    Args:
        value: The raw ``template=`` argument.

    Returns:
        ``True`` if *value* should be compiled as source, ``False`` if it
        should be resolved through the filesystem loader.
    """
    if not isinstance(value, str) or not value:
        return False
    if any(marker in value for marker in JINJA_MARKERS):
        return True
    return "\n" in value or "\r" in value
```
**Why this shape**: a verbatim move of `notify/templates.py:88-114` — body, docstring
and `#:` comment unchanged, so `tests/test_jinja_string_templates.py:94-132` keeps
passing untouched. The module docstring states the constraint so a future edit does
not casually re-import jinja2. No stdlib import is needed; do not add one.

### `notify/templates.py` (MODIFY — delete the originals)

```python
# occurrences: 1 (verified: grep -c '^JINJA_MARKERS' notify/templates.py)
# DELETE lines 88-89 (the `#:` comment + JINJA_MARKERS) and lines 95-114
# (the whole `is_template_source` function), verified: notify/templates.py:88-114.
# KEEP lines 91-92 — the `#:` comment and DEFAULT_STRING_CACHE_SIZE stay here.
```

```python
# occurrences: 1 (verified: grep -c 'from navconfig.logging import logging' notify/templates.py)
# AFTER — insert below `from navconfig.logging import logging` (verified: notify/templates.py:26)
from notify.utils.templates import JINJA_MARKERS, is_template_source

# Re-exported for backward compatibility: notify/providers/base.py and
# tests/test_jinja_string_templates.py:28-30 import both from here.
# The re-export MUST stay silent — pyproject.toml sets
# filterwarnings = ["error", ...], so any DeprecationWarning fails CI.
```
**Why**: one definition, two import paths. Placing the import with the other
module-level imports (rather than behind a `__getattr__`) is what keeps it silent
and keeps `from notify.templates import JINJA_MARKERS` a plain attribute lookup.
Flake8 may flag the names as unused — add `# noqa: F401` if your linter does,
rather than deleting the re-export.

### `notify/providers/base.py` (MODIFY)

```python
# occurrences: 1 (verified: grep -c 'from notify.models import Actor' notify/providers/base.py)
# REPLACE lines 18-19 (verified: notify/providers/base.py:18-19):
#     from notify.models import Actor
#     from notify.templates import is_template_source
# WITH:
from notify.utils.templates import is_template_source

if TYPE_CHECKING:
    from notify.models import Actor
```

```python
# occurrences: 1 (verified: grep -c '^import asyncio' notify/providers/base.py)
# BEFORE — `from __future__ import annotations` must be the FIRST statement after
# the module docstring, above `import asyncio` (verified: notify/providers/base.py:5)
from __future__ import annotations
```

```python
# occurrences: 1 (verified: grep -c 'from typing import Any, Union, Optional' notify/providers/base.py)
# REPLACE (verified: notify/providers/base.py:7)
from typing import Any, Union, Optional, TYPE_CHECKING
```
**Why**: `Actor` is an annotation at lines 119, 169, 189, 210, 228 and 265 and
nowhere else, so `TYPE_CHECKING` costs nothing at runtime and keeps type checkers
working. `is_template_source` moves to the jinja2-free path; its sole runtime call
site (line 155) is unchanged. Leave the docstring reference at line 135 pointing at
`notify.templates.is_template_source` — that path still resolves via the re-export.
`from navconfig import DEBUG` (line 12) is a **runtime** use at line 64 — do not touch it.

### `notify/providers/message.py` (MODIFY)

```python
# occurrences: 1 (verified: grep -c 'from notify.models import Actor' notify/providers/message.py)
# REPLACE line 6 (verified: notify/providers/message.py:6) with a TYPE_CHECKING guard,
# and add `from __future__ import annotations` as the first statement of the file
# (this module has no docstring — verified: notify/providers/message.py:1 is `import asyncio`).
from __future__ import annotations

import asyncio
from typing import Any, Union, TYPE_CHECKING
from collections.abc import Callable, Awaitable
from functools import partial
import threading

if TYPE_CHECKING:
    from notify.models import Actor
```
**Why**: the discovered gap. `rcpt: Actor` at line 15 is the module's only `Actor`
reference, so this is the same safe transformation as `base.py`. Skipping this file
leaves `datamodel` resident through `base.py:20`'s `from .message import
ThreadMessage` and silently defeats AC-G6.

### `notify/notify.py` (MODIFY)

```python
# occurrences: 1 (verified: grep -c '^import importlib' notify/notify.py)
# BEFORE — first statement of the module, above `import importlib`
from __future__ import annotations
```

```python
# DELETE the two module-level imports (verified pre-TASK-34: notify/notify.py:5 and :8):
#     from .conf import TEMPLATE_DIR
#     from .templates import TemplateParser
# Re-verify these line numbers after TASK-34 — it rewrites this file.
```

```python
# occurrences: 1 (verified: grep -c 'if name == "TemplateEnv":' notify/notify.py)
# AFTER — insert as the first statements inside the `if name == "TemplateEnv":`
# branch of __getattr__, above `global _TEMPLATE_ENV`
        from .conf import TEMPLATE_DIR            # noqa: PLC0415
        from .templates import TemplateParser     # noqa: PLC0415
```
**Why**: `__getattr__` is the sole consumer of both names — verified by grep. The
`__future__` import is not optional: `_TEMPLATE_ENV: TemplateParser | None = None`
is a module-level annotated assignment that would raise `NameError` at import time
without it. `__getattr__`'s contract, the `_TEMPLATE_ENV` memoisation slot and the
`TEMPLATE_DIR.exists()` warning all stay exactly as they are.

### FILL IN checklist

*(none — every block above is fully determined. If a line number has drifted
because TASK-34 landed first, re-verify with grep and adjust the anchor; do not
change any signature, path or name.)*

---

## Acceptance Criteria

- [ ] In a clean subprocess, `import notify` leaves **both** `jinja2` and
      `datamodel` out of `sys.modules`. *(AC-G6)*
- [ ] After `notify.TemplateEnv` (or a `_prepare_(template=...)` call), `jinja2`
      **is** in `sys.modules` — deferral, not deletion. *(AC-G6)*
- [ ] Importing `notify.utils.templates` in a clean subprocess leaves `jinja2`,
      `datamodel` and `navconfig` out of `sys.modules`.
- [ ] `from notify.templates import is_template_source, JINJA_MARKERS` works, with
      **no warning**, and `JINJA_MARKERS == ("{{", "{%", "{#")`.
- [ ] `notify/utils/functions.py` still has zero imports.
- [ ] Cold `import notify`, measured **after** `python setup.py build_ext --inplace`,
      is **≤ 175 ms** against a re-measured pre-change baseline on the same machine.
      Record the before/after pair in the Completion Note. If it lands above 175 ms,
      **report it — do not tune the threshold**. *(AC-G6)*
- [ ] `notify.__all__` unchanged.
- [ ] `PYTHONPATH=. pytest tests/ -v` passes — in particular
      `tests/test_jinja_string_templates.py` and `tests/test_templates_integration.py`
      pass **unmodified**.
- [ ] `black --line-length 120`, `flake8`, `pylint` clean on the changed files.

---

## Test Specification

TASK-39 writes `tests/test_startup_imports.py`. Self-verify with:

```bash
source .venv/bin/activate
python setup.py build_ext --inplace

# AC-G6 — must print: False False
python -c "import sys, notify; print('jinja2' in sys.modules, 'datamodel' in sys.modules)"

# Deferral, not deletion — must print: True
python -c "import sys, notify; notify.TemplateEnv; print('jinja2' in sys.modules)"

# The new module stays light — must print: False False False
python -c "import sys, notify.utils.templates as t; print(*( m in sys.modules for m in ('jinja2','datamodel','navconfig')))"

# Cold-import budget — record both numbers in the Completion Note
python -X importtime -c "import notify" 2>&1 | tail -1

PYTHONPATH=. pytest tests/test_jinja_string_templates.py tests/test_templates_integration.py -v
```

> Measure the **baseline first**, on the same machine, before your edits — AC-G6
> asks for a before/after pair, not an absolute number quoted from the spec.

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** §2 ("Revised import-cost budget"), §3 Module 3, §5 (G6) and §7.
2. **Check dependencies** — TASK-34 must be in `sdd/tasks/completed/`. It rewrites
   `notify/notify.py`, so **re-verify every line number in this task's contract**
   against the current file before editing.
3. **Verify the Codebase Contract**, then record the pre-change baseline.
4. Update this feature's index entry to `in-progress`.
5. **Implement** from the blueprint, in the listed order.
6. **Verify** every acceptance criterion; rebuild Cython before measuring.
7. **Move this file** to `sdd/tasks/completed/`.
8. **Update** `sdd/tasks/index/lazy-import-providers.json` → `"done"`.
9. **Fill in the Completion Note**, including the before/after import timings.

---

## Completion Note

*(Agent fills this in when done)*

**Completed by**: <session or agent ID>
**Date**: YYYY-MM-DD
**Import cost**: before `___ ms` → after `___ ms` (threshold ≤ 175 ms)
**Notes**:

**Deviations from spec**: `notify/providers/message.py` added to M3's file list —
spec §3 M3 omitted it, but its annotation-only `Actor` import keeps `datamodel`
resident and blocks AC-G6.

### Completion Note
Created notify/utils/templates.py; notify/templates.py re-exports silently; base.py and message.py use TYPE_CHECKING for Actor; notify.py defers conf/TemplateParser into `__getattr__` with `from __future__ import annotations`. `import notify` → jinja2/datamodel both False; after `notify.notify.TemplateEnv` jinja2 True. Full suite: 329 passed (2 pre-existing test_ses failures).
Timing (`python -X importtime -c "import notify"`, after build_ext): before ≈ 214-217 ms, after ≈ 171-176 ms (runs: 176.0, 175.6, 174.6, 174.5, 171.3). Borderline vs the ≤175 ms target — reported, threshold not tuned.
Deviation to note: the AC "importing notify.utils.templates leaves navconfig out of sys.modules" cannot hold as written — importing any `notify.*` submodule runs `notify/__init__.py`, which imports navconfig (out of scope per spec §1). jinja2 and datamodel are absent as required.
