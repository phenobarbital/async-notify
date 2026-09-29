# TASK-39: Prove the startup deferrals in a clean subprocess

**Feature**: FEAT-005 — Actionable optional-dependency diagnostics and a slim core install
**Spec**: `sdd/specs/lazy-import-providers.spec.md`
**Status**: pending
**Priority**: medium
**Estimated effort**: M (2-4h)
**Depends-on**: TASK-35
**Assigned-to**: unassigned

---

## Context

Implements the **M3 slice of spec §3 Module 5**, locking goal **G6**.

Spec §4 is emphatic that **a subprocess is mandatory** here: the existing suite
(`tests/test_jinja_string_templates.py:28`, `tests/test_templates_integration.py`)
imports `TemplateParser` and `TemplateEnv` at collection time, so `jinja2` is
resident long before any in-process `sys.modules` assertion would run. An
in-process check would be vacuous — green for the wrong reason, forever.

This task also pins the **accepted behaviour change** from TASK-35: `Actor` no
longer resolves through `typing.get_type_hints()`. Spec §7 asks for exactly that
("add a test that pins the new behaviour, so it is a decision rather than a
surprise").

---

## Scope

- Create `tests/test_startup_imports.py` with the three integration tests and the
  two M3 unit tests named in spec §4, plus the `get_type_hints` pin.

**NOT in scope**: `tests/test_provider_dependencies.py` (TASK-37),
`tests/test_dependency_manifest.py` (TASK-38), any change under `notify/`
(TASK-35 owns it — if a test fails, fix the deferral, not the test). Do not modify
`tests/test_jinja_string_templates.py` or `tests/test_templates_integration.py`.

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `tests/test_startup_imports.py` | CREATE | Subprocess startup-purity + budget + re-export tests |

---

## Codebase Contract (Anti-Hallucination)

> Verified against `dev` @ `d72fe6e` on 2026-09-29. Symbols marked **(TASK-35)**
> do not exist until that task lands.

### Verified Imports

```python
import subprocess, sys, warnings                             # stdlib
from notify.templates import is_template_source, JINJA_MARKERS  # verified: notify/templates.py:89,95
from notify.utils.templates import is_template_source        # (TASK-35) — new module
```

### Measured baseline on `dev` (reproduce before asserting)

```bash
$ python -c "import sys, notify; print('jinja2' in sys.modules, 'datamodel' in sys.modules)"
True True        # <- today. Must be `False False` after TASK-35.
```

### Existing facts

```python
# notify/templates.py
JINJA_MARKERS: tuple[str, ...] = ("{{", "{%", "{#")   # line 89 — exact value asserted below
# notify/notify.py
def __getattr__(name: str):    # PEP 562 hook; `notify.TemplateEnv` is the trigger for first template use

# notify/providers/base.py
class ProviderBase(ABC):                                    # line 31
    async def _prepare_(self, recipient: Actor = None, ...) # line 117 — Actor annotation
# notify/providers/message.py
class ThreadMessage(threading.Thread):                      # line 9
    def __init__(self, ..., rcpt: Actor, ...)               # line 15 — Actor annotation
```

### Test-suite facts

- `pytest.ini` is the **effective** config; pytest prints
  `configfile: pytest.ini (WARNING: ignoring pytest config in pyproject.toml!)`
  on every run. It sets `filterwarnings = ignore::DeprecationWarning` — the
  **opposite** of the `error` filter spec §3 M3 and §7 assume. See below.
- Declared markers: `integration`, `live`, `real_llm` only. This file needs none —
  a subprocess running `sys.executable` is not an external service.
- There is **no** `tests/conftest.py`.

### Does NOT Exist

- ~~an `error` filterwarnings setting in effect~~ — `pyproject.toml`'s
  `filterwarnings = ["error", ...]` is **ignored** because `pytest.ini` exists.
  The silent-re-export requirement must be asserted explicitly, not assumed.
- ~~`notify.utils.templates`~~ — TASK-35 creates it.
- ~~an in-process way to prove cold-start absence~~ — spec §4 rules it out; use
  `subprocess.run([sys.executable, "-c", ...])`.
- ~~`pytest-benchmark`~~ — not a dependency. Time with `time.perf_counter` in the
  subprocess, or parse `python -X importtime`.

---

## Implementation Notes

### The silent re-export needs a real assertion

Because `pytest.ini` wins and sets `ignore::DeprecationWarning`, a warning from the
`notify.templates` re-export would pass CI unnoticed. Assert it directly with
`warnings.catch_warnings(record=True)` + `simplefilter("always")` **in a
subprocess** (an in-process import is already cached and would record nothing).

### The import-budget test is environment-sensitive

AC-G6 sets **≤ 175 ms**, but that number was measured on the spec author's machine.
A cold CI runner or a loaded laptop can exceed it for reasons unrelated to this
change, and a flaky perf test that gets `@skip`-ed is worse than none.

Make it robust rather than lenient:
- measure in a subprocess, take the **minimum** of 3-5 runs (minimum, not mean —
  it is the least noise-contaminated estimate),
- assert the absolute `≤ 175 ms` threshold,
- and on failure print the measured value **and** the `jinja2`/`datamodel` absence
  result, so a reader can tell "slow machine" from "deferral regressed".

If it proves flaky in CI, raise it with the user — spec §5 says explicitly: *"If
the measurement lands above 175 ms, report it rather than tuning the threshold."*
That instruction is binding on this task too.

### Key Constraints

- Every `sys.modules` assertion runs in a subprocess started from `sys.executable`,
  with `cwd` at the repo root and `PYTHONPATH=.` so the worktree's `notify` is the
  one imported — not the copy installed in the shared `.venv`.
- The Cython extension must be built (`python setup.py build_ext --inplace`) before
  any measurement; spec §7 says a measurement against stale `.so` files is invalid.
- Keep each subprocess snippet a one-liner passed to `-c`, or a small `textwrap.dedent`
  block — do not write temp files.
- Google-style docstrings, `black --line-length 120`.

---

## Implementation Blueprint

### Steps (in order)

1. Write a `_run(code)` helper returning the subprocess's stdout — *why*: five tests
   need the same "clean interpreter, repo root, `PYTHONPATH=.`" setup, and getting
   it wrong once is getting it wrong everywhere.
2. Write the two purity tests — *why*: they are AC-G6's core claim.
3. Write the "loads on first use" test — *why*: it is what distinguishes deferral
   from deletion; without it, deleting jinja2 support entirely would pass.
4. Write the re-export and `get_type_hints` tests — *why*: the two compatibility
   contracts TASK-35 puts at risk.
5. Write the budget test last — *why*: it is the noisiest, and the others localise
   a failure better.

### `tests/test_startup_imports.py` (CREATE)

```python
"""Startup-import deferral tests (FEAT-005, M3).

Locks spec §5 goal G6. Every `sys.modules` assertion runs in a CLEAN
SUBPROCESS: the existing suite imports TemplateParser and TemplateEnv at
collection time (tests/test_jinja_string_templates.py:28,
tests/test_templates_integration.py), so an in-process check would be
vacuous — see spec §4.
"""
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Modules that must NOT be resident after a bare `import notify`.
DEFERRED = ("jinja2", "datamodel")

#: AC-G6 cold-import ceiling, in milliseconds.
IMPORT_BUDGET_MS = 175.0


def _run(code: str) -> str:
    """Run *code* in a clean interpreter rooted at the repo and return stdout.

    Args:
        code: Python source executed via ``-c``.

    Returns:
        Stripped stdout. Raises ``AssertionError`` with stderr attached when
        the child exits non-zero, so a failure shows the traceback.
    """
    # FILL IN: subprocess.run([sys.executable, "-c", textwrap.dedent(code)],
    # cwd=REPO_ROOT, capture_output=True, text=True, and env with PYTHONPATH="."
    # merged over os.environ. Assert returncode == 0, attaching result.stderr
    # to the message. Bounded by the Key Constraints above — PYTHONPATH="." is
    # what makes the worktree's `notify` win over the one installed in .venv.
    raise NotImplementedError


def test_import_notify_defers_heavy_modules():
    """AC-G6 — `import notify` leaves jinja2 and datamodel out of sys.modules."""
    out = _run(
        """
        import sys
        import notify
        print(" ".join(m for m in ("jinja2", "datamodel") if m in sys.modules) or "clean")
        """
    )
    assert out == "clean", f"still resident after `import notify`: {out}"


def test_deferred_modules_load_on_first_use():
    """AC-G6 — deferral, not deletion: jinja2 appears after first template use."""
    # FILL IN: in one subprocess, `import notify`, assert jinja2 absent, then
    # touch `notify.TemplateEnv` (the PEP 562 hook) and print whether jinja2 is
    # now resident. Assert it IS. Bounded by AC-G6 ("both appear after first
    # template use"). Note TemplateEnv construction warns when TEMPLATE_DIR is
    # missing — that is expected and must not fail the child.
    raise NotImplementedError


def test_utils_templates_has_no_heavy_imports():
    """Importing notify.utils.templates pulls in no heavy module."""
    out = _run(
        """
        import sys
        import notify.utils.templates  # noqa: F401
        heavy = [m for m in ("jinja2", "datamodel", "navconfig") if m in sys.modules]
        print(" ".join(heavy) or "clean")
        """
    )
    assert out == "clean", f"notify.utils.templates dragged in: {out}"


def test_is_template_source_reexported():
    """The compatibility re-export works, SILENTLY, with the same value."""
    # FILL IN: in a subprocess, use warnings.catch_warnings(record=True) +
    # simplefilter("always") around
    # `from notify.templates import is_template_source, JINJA_MARKERS`;
    # print the number of warnings and the JINJA_MARKERS value. Assert zero
    # warnings and JINJA_MARKERS == ("{{", "{%", "{#").
    # A subprocess is required: an in-process import is already cached and
    # records nothing. Bounded by the AC "still works, silently" — and note
    # pytest.ini's `ignore::DeprecationWarning` means nothing else will catch
    # a regression here.
    raise NotImplementedError


def test_actor_annotation_no_longer_resolves():
    """Pin the ACCEPTED behaviour change from spec §7.

    ``typing.get_type_hints()`` on ProviderBase / ThreadMessage methods no
    longer resolves ``Actor``: PEP 563 makes it a string and the deferred
    ``TYPE_CHECKING`` import means module globals cannot resolve it. The repo
    has zero ``get_type_hints`` callers; this test makes the change a recorded
    decision rather than a surprise.
    """
    # FILL IN: assert typing.get_type_hints(ProviderBase._prepare_) raises
    # NameError, and that importing notify.models first makes it resolvable
    # again (the documented workaround in CHANGES.rst). Bounded by spec §7
    # "add a test that pins the new behaviour". If TASK-35 chose a shape that
    # keeps it resolving, invert this test and say so in the Completion Note —
    # do NOT delete it.
    raise NotImplementedError


def test_import_notify_within_budget():
    """AC-G6 — cold `import notify` stays within the spec threshold."""
    # FILL IN: run the import in a subprocess 3-5 times, timing with
    # time.perf_counter INSIDE the child (so interpreter startup is excluded),
    # take the MINIMUM, and assert it <= IMPORT_BUDGET_MS. On failure include
    # the measured value AND the DEFERRED-module residency, so a slow machine
    # is distinguishable from a regressed deferral.
    # Bounded by AC-G6 and by spec §5: "If the measurement lands above 175 ms,
    # report it rather than tuning the threshold."
    raise NotImplementedError
```
**Why this shape**: spec §4's three integration rows plus its two M3 unit rows,
plus the §7 `get_type_hints` pin. `_run` centralises the subprocess contract
because `PYTHONPATH="."` is the single thing that decides whether the test measures
the worktree or the installed copy — spec §7 and the worktree rule both warn about
this. `DEFERRED` and `IMPORT_BUDGET_MS` are module constants so the threshold
appears once and a future change is a one-line, reviewable diff rather than a
number buried in an assertion.

### FILL IN checklist

- [ ] `_run` — clean subprocess, `cwd=REPO_ROOT`, `PYTHONPATH="."`, stderr on failure.
- [ ] `test_deferred_modules_load_on_first_use` — absent, then present after
      `notify.TemplateEnv`; AC-G6.
- [ ] `test_is_template_source_reexported` — zero warnings + exact `JINJA_MARKERS`.
- [ ] `test_actor_annotation_no_longer_resolves` — pin the accepted change; spec §7.
- [ ] `test_import_notify_within_budget` — min of 3-5 runs, ≤ 175 ms, diagnostic
      failure message; AC-G6.

---

## Acceptance Criteria

- [ ] All six tests exist and pass:
      `PYTHONPATH=. pytest tests/test_startup_imports.py -v`
- [ ] Every `sys.modules` assertion runs in a subprocess — grep the file: no
      `sys.modules` check outside a `_run` snippet.
- [ ] The tests pass when run **after** the rest of the suite
      (`PYTHONPATH=. pytest tests/ -v`), proving they are not sensitive to what
      collection already imported.
- [ ] The budget test measures **after** `python setup.py build_ext --inplace`, and
      the measured value is recorded in the Completion Note.
- [ ] No test is `@pytest.mark.skip`-ed to make the budget pass.
- [ ] `black --line-length 120`, `flake8`, `pylint` clean on the new file.

---

## Test Specification

Spec §4's M3 rows, reproduced:

| Test | Asserts |
|---|---|
| `test_import_notify_defers_heavy_modules` | Clean subprocess: `import notify` leaves `jinja2`, `datamodel` out of `sys.modules` |
| `test_deferred_modules_load_on_first_use` | After `notify.TemplateEnv`, `jinja2` **is** resident |
| `test_import_notify_within_budget` | Cold `import notify` ≤ 175 ms |
| `test_is_template_source_reexported` | `from notify.templates import is_template_source, JINJA_MARKERS` works silently; markers `== ("{{", "{%", "{#")` |
| `test_utils_templates_has_no_heavy_imports` | `notify.utils.templates` leaves `jinja2`, `datamodel`, `navconfig` out |
| `test_actor_annotation_no_longer_resolves` | The accepted `get_type_hints` change (spec §7) |

Run:
```bash
source .venv/bin/activate
python setup.py build_ext --inplace
PYTHONPATH=. pytest tests/test_startup_imports.py -v
PYTHONPATH=. pytest tests/ -v          # must also pass in full-suite order
```

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** §2 ("Revised import-cost budget"), §3 Module 3, §4 (including
   the subprocess note) and §5 (G6).
2. **Check dependencies** — TASK-35 must be in `sdd/tasks/completed/`, and the
   Cython extension rebuilt.
3. **Verify the Codebase Contract** — confirm `notify/utils/templates.py` exists and
   reproduce the baseline probe.
4. Update this feature's index entry to `in-progress`.
5. **Implement** from the blueprint; resolve every `FILL IN`. If a purity test
   fails, fix the deferral in `notify/` — never weaken the assertion.
6. **Verify** every acceptance criterion, including full-suite ordering.
7. **Move this file** to `sdd/tasks/completed/`.
8. **Update** `sdd/tasks/index/lazy-import-providers.json` → `"done"`.
9. **Fill in the Completion Note**, including the measured import cost.

---

## Completion Note

*(Agent fills this in when done)*

**Completed by**: <session or agent ID>
**Date**: YYYY-MM-DD
**Measured cold import**: `___ ms` (budget ≤ 175 ms)
**Notes**:

**Deviations from spec**: none | describe if any

### Completion Note
Created tests/test_startup_imports.py: 6 tests, every sys.modules assertion in a clean subprocess (`PYTHONPATH=.`, cwd=repo root). Pass alone and after the full suite (355 passed; 2 pre-existing test_ses failures).
**Measured cold import** (in-child perf_counter, after build_ext, min of 5): ~152-156 ms (budget ≤ 175 ms).
Deviations: (1) test_utils_templates_has_no_heavy_imports asserts jinja2/datamodel only — navconfig cannot be absent because importing any `notify.*` submodule runs notify/__init__.py, which imports navconfig (out of scope, spec §1). (2) test_actor_annotation pins NameError for ProviderBase._prepare_ and ThreadMessage.__init__ and shows the workaround (`localns={"Actor": Actor}`); CHANGES.rst wording says "import notify.models.Actor explicitly", which alone does not make get_type_hints resolve — passing it via localns does. Consider rewording CHANGES.rst.
