# TASK-009: Fix add_filter() name resolution and normalise the error prefix

**Feature**: FEAT-002 — TemplateParser refactor (homologation with ai-parrot TemplateEngine)
**Spec**: `sdd/specs/templateparser-refactor.spec.md`
**Status**: pending
**Priority**: high
**Estimated effort**: S (< 2h)
**Depends-on**: TASK-008
**Assigned-to**: unassigned

---

## Context

Implements **Module 3** of the spec (§3). Two defects found during the
comparative audit against ai-parrot, both in `notify/templates.py`:

1. **`add_filter()` is unconditionally broken when `name` is omitted.** At
   `notify/templates.py:94`, inside the `elif callable(func):` branch, the code
   reads `filter_name = name.__name__` — but `name` is provably `None` on that
   branch (the `if name is not None:` above already returned). Any
   `add_filter(func)` call raises
   `AttributeError: 'NoneType' object has no attribute '__name__'`.
   It must read `func.__name__`.

2. **Inconsistent error prefix.** `notify/templates.py:129` raises with
   `"NAV: Error rendering: ..."` while every other error in the module uses the
   `"Notify: "` prefix.

The `add_filter` bug is latent — `grep -rn 'add_filter' notify/` returns only
the definition, no callers — so this is a correctness fix, not an outage fix.

---

## Scope

- Fix `notify/templates.py:94`: `name.__name__` → `func.__name__`.
- Make the non-callable branch reachable and correct: raise `TypeError` when
  `func` is not callable (today the `elif callable(func)` / `else` structure
  means a non-callable with an explicit `name` is silently accepted).
- Re-implement `add_filter(func, name=None)` as a thin delegation to
  `add_filters({resolved_name: func})` from TASK-008, so there is one
  registration path.
- Normalise the `"NAV: "` prefix at `notify/templates.py:129` to `"Notify: "`.
- Audit the whole module for any other non-`"Notify: "` error prefix and
  normalise it.

**NOT in scope**: any other behaviour change; `notify/notify.py` (TASK-010);
packaging (TASK-011); tests (TASK-012, TASK-013).

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `notify/templates.py` | MODIFY | Fix `add_filter`; normalise error prefixes |

---

## Codebase Contract (Anti-Hallucination)

### Verified Imports

```python
from collections.abc import Callable   # notify/templates.py:3 — already present
from typing import Optional            # notify/templates.py:2 — already present
```

### Existing Signatures to Use

```python
# notify/templates.py:87-97 — THE DEFECT, verbatim from the working tree
def add_filter(self, func: Callable, name: Optional[str] = None) -> None:
    """add_filter.
    Register a custom function as Template Filter.
    """
    if name is not None:
        filter_name = name
    elif callable(func):
        filter_name = name.__name__        # line 94 ← BUG: `name` is None here
    else:
        raise TypeError(f"Template Filter must be a callable function: {func!r}")
    self.env.filters[filter_name] = func
```

```python
# notify/templates.py:112-130 — the "NAV: " prefix
async def render_async(self, filename: str, params: Optional[dict] = None) -> str:
    ...
    except TemplateError as ex:
        raise ValueError(
            f"Template parsing error, template: {filename}: {ex}"
        ) from ex
    except Exception as err:
        raise RuntimeError(
            f"NAV: Error rendering: {filename}, error: {err}"   # line 129 ← BUG
        ) from err
```

```python
# The correct prefix used everywhere else in the module:
# line 31  → f"Notify: template directory {directory} does not exist"
# line 61  → f"Notify: Error loading Template Environment: {err}"
# line 109 → f"Notify: Error rendering template: {filename}, error: {err}"
```

```python
# Available from TASK-008 — delegate to it
def add_filters(self, filters: Mapping[str, Callable]) -> None: ...
```

### Does NOT Exist

- ~~Any caller of `TemplateParser.add_filter()`~~ — verified with
  `grep -rn 'add_filter' notify/ tests/ examples/`: only the definition at
  `templates.py:87`. The bug is latent; fixing it breaks nothing.
- ~~`TemplateEngine.add_filter()` in ai-parrot~~ — ai-parrot only has
  `add_filters(mapping)` (`engine.py:210`). There is no upstream singular
  variant to copy from.
- ~~A `"NAV: "` prefix anywhere else in `notify/`~~ — verify with
  `grep -rn '"NAV:' notify/` before assuming; only `templates.py:129` was found.

---

## Implementation Notes

### Pattern to Follow

```python
def add_filter(self, func: Callable, name: Optional[str] = None) -> None:
    """Register a single callable as a Jinja2 template filter.

    Args:
        func: The callable to register.
        name: Filter name. Defaults to ``func.__name__``.

    Raises:
        TypeError: If ``func`` is not callable.
    """
    if not callable(func):
        raise TypeError(
            f"Notify: Template Filter must be a callable function: {func!r}"
        )
    self.add_filters({name or func.__name__: func})
```

Note the ordering change: callability is checked **first**, so a non-callable
is rejected even when an explicit `name` is supplied. The current structure
lets `add_filter("not-a-function", name="x")` through silently.

### Key Constraints

- Preserve the public signature `add_filter(self, func, name=None) -> None`.
- Do not change `render_async`'s exception *types* — only the message prefix.
  `TemplateError` → `ValueError`, everything else → `RuntimeError`.
- Google-style docstring with `Args:` and `Raises:`.

### References in Codebase

- `notify/templates.py:87-97` — the method being fixed.
- `notify/templates.py:99-110` — `render()`, which already uses the correct
  `"Notify: "` prefix; mirror its wording.

---

## Acceptance Criteria

- [ ] `add_filter(my_func)` registers the filter under `"my_func"` and does not raise
- [ ] `add_filter(my_func, name="custom")` registers under `"custom"`
- [ ] `add_filter("not-callable")` raises `TypeError`
- [ ] `add_filter("not-callable", name="x")` also raises `TypeError`
- [ ] `add_filter` delegates to `add_filters` (single registration path)
- [ ] `grep -n '"NAV:' notify/templates.py` returns nothing
- [ ] `grep -rn 'NAV:' notify/` returns nothing outside of legitimate Jira references
- [ ] `render_async` failure messages start with `"Notify:"`
- [ ] Exception types raised by `render_async` are unchanged (`ValueError` / `RuntimeError`)
- [ ] `ruff check notify/templates.py` clean

---

## Test Specification

Tests are written in TASK-012 (`test_add_filter_without_name_uses_func_name` is
the regression test for the `:94` defect). Verify manually:

```python
def shout(v): return str(v).upper()

p = TemplateParser(directory=d)
p.add_filter(shout)                      # must NOT raise AttributeError
assert "shout" in p.environment.filters

p.add_filter(shout, name="yell")
assert "yell" in p.environment.filters

try:
    p.add_filter("nope")
except TypeError:
    pass
else:
    raise AssertionError("expected TypeError")
```

---

## Agent Instructions

1. **Read the spec** — §1 (the two defects), §3 Module 3, §5.
2. **Check dependencies** — TASK-008 must be in `sdd/tasks/completed/`
   (`add_filter` delegates to `add_filters`).
3. **Verify the Codebase Contract** — re-read `notify/templates.py` and confirm
   the defect is still at the stated lines; TASK-007/008 will have shifted them.
4. **Update status** in `sdd/tasks/index/templateparser-refactor.json` → `in-progress`.
5. **Implement** the scope. Nothing beyond it.
6. **Verify** every acceptance criterion.
7. **Move this file** to `sdd/tasks/completed/TASK-009-defect-fixes.md`.
8. **Update index** → `done`.
9. **Fill in the Completion Note**.

Use `.venv/bin/python` directly — `.venv/bin/activate` is stale.

---

## Completion Note

**Completed by**: sdd-worker (Claude)
**Date**: 2026-08-06
**Notes**: Fixed `add_filter()` to check `callable(func)` first (raising
`TypeError` even when an explicit `name` is supplied to a non-callable),
then delegates to `add_filters({name or func.__name__: func})` from
TASK-008 — single registration path, defect at the old `name.__name__`
line eliminated. Normalised the sole `"NAV: "` prefix (in `render_async`'s
generic exception handler) to `"Notify: "`; confirmed via
`grep -rn 'NAV:' notify/` that no other occurrence exists. Exception types
in `render_async` unchanged (`ValueError` for `TemplateError`, `RuntimeError`
otherwise). Verified manually per the task's Test Specification.
`ruff check notify/templates.py` clean. Full `pytest tests/ -v`: 59 passed,
2 failed + 3 errors, all pre-existing on the `dev` baseline, unrelated to
this change.

**Deviations from spec**: none
