# TASK-010: Lazy TemplateEnv singleton via PEP 562

**Feature**: FEAT-002 — TemplateParser refactor (homologation with ai-parrot TemplateEngine)
**Spec**: `sdd/specs/templateparser-refactor.spec.md`
**Status**: pending
**Priority**: high
**Estimated effort**: M (2-4h)
**Depends-on**: TASK-007
**Assigned-to**: unassigned

---

## Context

Implements **Module 4** of the spec (§3). Today `notify/notify.py:83-87`
constructs the `TemplateEnv` singleton at module import:

```python
if __name__ == "notify.notify":
    TemplateEnv = TemplateParser(directory=TEMPLATE_DIR)
```

Combined with `TemplateParser.__init__` raising `RuntimeError` on a missing
directory (`templates.py:29-32`), this means **importing `notify` fails outright
in any environment without a `templates/` directory** — a hard import-time
dependency on filesystem state. TASK-007 already made the parser tolerate an
absent directory; this task removes the eager construction.

---

## Scope

- Delete `TemplateEnv = None` at `notify/notify.py:10`.
- Delete the `if __name__ == "notify.notify":` block at `notify/notify.py:83-87`.
- Add a module-level `__getattr__(name)` (PEP 562) that builds the
  `TemplateParser` on first access to `TemplateEnv` and memoises it in a
  module-private slot.
- Log a warning (not an exception) when `TEMPLATE_DIR` does not exist; the
  memoised parser then runs in memory-only mode.
- Add a `__dir__()` so `TemplateEnv` still shows up in introspection.
- Keep `from notify.notify import TemplateEnv` working unchanged for
  `notify/providers/base.py:66`.

**NOT in scope**: any change to `notify/templates.py` (TASK-007, 008, 009); any
change to `notify/providers/base.py`; packaging (TASK-011); tests (TASK-012,
TASK-013).

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `notify/notify.py` | MODIFY | Remove eager init; add PEP 562 `__getattr__` + `__dir__` |

---

## Codebase Contract (Anti-Hallucination)

### Verified Imports

```python
# notify/notify.py:1-6 — current imports, all still needed
import importlib
from navconfig.logging import logger
from .providers.base import ProviderBase
from .exceptions import ProviderError, NotifyException
from .conf import TEMPLATE_DIR
from .templates import TemplateParser
```

### Existing Signatures to Use

```python
# notify/notify.py — current state, 88 lines
PROVIDERS = {}                                     # line 9
TemplateEnv = None                                 # line 10  ← DELETE THIS LINE

class Notify:                                      # line 12
    def __new__(cls, provider: str, *args, **kwargs): ...     # line 25
    @classmethod
    def provider(cls, provider: str, *args, **kwargs): ...    # line 45

def LoadProvider(provider: str): ...               # line 64

if __name__ == "notify.notify":                    # line 83  ← DELETE THIS BLOCK
    # loading template parser:
    TemplateEnv = TemplateParser(                  # line 85
        directory=TEMPLATE_DIR                     # line 86
    )
```

```python
# notify/providers/base.py:64-72 — the ONLY consumer. Do NOT modify this file.
# add the Jinja Template Parser
try:
    from notify.notify import TemplateEnv  # pylint: disable=C0415   # line 66
    self._tpl = TemplateEnv                                          # line 67
    self._template = None                                            # line 68
except Exception as err:
    raise RuntimeError(
        f"Notify: Can't load the Jinja2 Template Parser: {err}"
    ) from err

# notify/providers/base.py:142 — the only method called on the parser
self._template = self._tpl.get_template(template)
```

```python
# notify/conf.py:6-10 — TEMPLATE_DIR is always a Path, may not exist on disk
if not (template_dir := config.get('TEMPLATE_DIR')):
    TEMPLATE_DIR = BASE_DIR.joinpath("templates")
else:
    TEMPLATE_DIR = Path(template_dir).resolve()
```

### Does NOT Exist

- ~~A lazy-loading helper anywhere in `notify/`~~ — there is no existing
  precedent in this repo; you are introducing the pattern.
- ~~`notify.notify.get_template_env()`~~ — do not invent a new public function
  unless you also keep `TemplateEnv` working; `base.py:66` imports the *name*.
- ~~`TemplateEnv` as a class~~ — it is a `TemplateParser` *instance*.
- ~~Any consumer of `TemplateEnv` outside `notify/providers/base.py:66`~~ —
  verified with `grep -rn 'TemplateEnv' notify/ tests/ examples/`.
- ~~`notify/__init__.py` re-exporting `TemplateEnv`~~ — verify with
  `grep -n 'TemplateEnv' notify/__init__.py` before assuming either way.

---

## Implementation Notes

### Pattern to Follow

```python
_TEMPLATE_ENV: Optional[TemplateParser] = None


def __getattr__(name: str):
    """PEP 562 module-level attribute hook.

    Builds the shared :class:`TemplateParser` on first access to
    ``TemplateEnv`` and memoises it, so importing :mod:`notify` never
    touches the filesystem.
    """
    if name == "TemplateEnv":
        global _TEMPLATE_ENV
        if _TEMPLATE_ENV is None:
            if not TEMPLATE_DIR.exists():
                logger.warning(
                    "Notify: template directory %s does not exist; "
                    "TemplateEnv starts in memory-only mode.", TEMPLATE_DIR
                )
            _TEMPLATE_ENV = TemplateParser(directory=TEMPLATE_DIR)
        return _TEMPLATE_ENV
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted([*globals().keys(), "TemplateEnv"])
```

### Key Constraints

- **`__getattr__` only fires for names NOT already bound in the module.**
  Leaving `TemplateEnv = None` at line 10 makes the hook dead code that always
  returns `None`, and every provider would then fail at
  `self._tpl.get_template(...)` with `AttributeError: 'NoneType'`. Deleting
  line 10 is mandatory, not cosmetic (spec §7 R5).
- Requires Python ≥ 3.7 for PEP 562 — the project targets 3.11 (`.venv` is
  3.11.15), so this is safe.
- The `RuntimeError` wrapper at `base.py:69-72` still catches construction
  failures, so a genuinely broken template setup still surfaces clearly — just
  at first provider instantiation instead of at import.
- Use the module-level `logger` already imported at `notify/notify.py:2`.
- Do not make `__getattr__` thread-safe with a lock unless you can show a real
  race; double-construction is harmless here (last writer wins, both are
  equivalent parsers). Note the decision in the Completion Note.

### References in Codebase

- `notify/notify.py:83-87` — the block being removed.
- `notify/providers/base.py:64-72` — the consumer whose behaviour must not change.

---

## Acceptance Criteria

- [ ] `TemplateEnv = None` no longer exists at module scope in `notify/notify.py`
- [ ] The `if __name__ == "notify.notify":` block is gone
- [ ] `import notify.notify` constructs NO `TemplateParser` (verifiable by patching `TemplateParser.__init__` with a counter)
- [ ] `from notify.notify import TemplateEnv` returns a `TemplateParser` instance
- [ ] Two consecutive accesses return the *same* object (memoised)
- [ ] `import notify` succeeds when `TEMPLATE_DIR` points at a nonexistent path, emitting a warning
- [ ] `notify.notify.SomethingElse` raises `AttributeError` with a clear message
- [ ] `"TemplateEnv" in dir(notify.notify)` is `True`
- [ ] A `ProviderBase` subclass still resolves templates via `self._tpl.get_template()`
- [ ] `notify/providers/base.py` is UNCHANGED
- [ ] `ruff check notify/notify.py` clean

---

## Test Specification

Tests are written in TASK-013. Verify manually:

```python
import notify.notify as nn

assert "TemplateEnv" not in vars(nn)         # not eagerly bound
env1 = nn.TemplateEnv
env2 = nn.TemplateEnv
assert env1 is env2                          # memoised

from notify.templates import TemplateParser
assert isinstance(env1, TemplateParser)

try:
    nn.NotAThing
except AttributeError:
    pass
else:
    raise AssertionError("expected AttributeError")
```

---

## Agent Instructions

1. **Read the spec** — §2 Integration Points, §3 Module 4, §7 R5.
2. **Check dependencies** — TASK-007 must be in `sdd/tasks/completed/`; this
   task relies on the parser tolerating an absent directory.
3. **Verify the Codebase Contract** — re-read `notify/notify.py` and
   `notify/providers/base.py:64-72` before editing.
4. **Update status** in `sdd/tasks/index/templateparser-refactor.json` → `in-progress`.
5. **Implement** the scope. Do NOT touch `notify/providers/base.py`.
6. **Verify** every acceptance criterion.
7. **Move this file** to `sdd/tasks/completed/TASK-010-lazy-template-env.md`.
8. **Update index** → `done`.
9. **Fill in the Completion Note**, including the thread-safety decision.

Use `.venv/bin/python` directly — `.venv/bin/activate` is stale.

---

## Completion Note

**Completed by**: sdd-worker (Claude)
**Date**: 2026-08-06
**Notes**: Deleted `TemplateEnv = None` and the `if __name__ ==
"notify.notify":` eager-construction block. Added a module-private
`_TEMPLATE_ENV` memoisation slot plus PEP 562 `__getattr__`/`__dir__`.
`__getattr__` builds and memoises the `TemplateParser` on first access to
`TemplateEnv`, logging a warning (not raising) when `TEMPLATE_DIR` is
missing — the parser then runs in memory-only mode courtesy of TASK-007.
`notify/providers/base.py` was left untouched, as required; verified via
`git diff --stat` showing zero changes there. No thread-safety lock was
added around the memoisation — double construction on a race is harmless
(last writer wins, both are equivalent parsers), per the task's own
guidance. Verified manually: `import notify.notify` constructs zero
`TemplateParser` instances (patched-counter check), `TemplateEnv` accesses
are memoised (`is` identity across two accesses), unknown attributes raise
`AttributeError`, `"TemplateEnv" in dir(notify.notify)` is `True`, and
`import notify` succeeds with a nonexistent `TEMPLATE_DIR` (warning
logged, memory-only mode confirmed via `.path is None`). `ruff check
notify/notify.py` clean. Full `pytest tests/ -v`: 59 passed, 2 failed + 3
errors, identical to the pre-existing `dev` baseline.

**Deviations from spec**: none
