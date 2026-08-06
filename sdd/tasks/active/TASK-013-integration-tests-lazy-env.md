# TASK-013: Integration tests — lazy TemplateEnv and the provider render path

**Feature**: FEAT-002 — TemplateParser refactor (homologation with ai-parrot TemplateEngine)
**Spec**: `sdd/specs/templateparser-refactor.spec.md`
**Status**: pending
**Priority**: high
**Estimated effort**: M (2-4h)
**Depends-on**: TASK-010, TASK-012
**Assigned-to**: unassigned

---

## Context

Implements the integration half of **Module 6** (spec §3, §4). TASK-012 covers
`TemplateParser` in isolation; this task proves the two seams that the refactor
actually moved:

1. **The lazy singleton** — `notify.notify.TemplateEnv` must no longer be built
   at import, must be memoised, and must let `import notify` succeed without a
   `templates/` directory (spec §1 G8, §7 R5).
2. **The provider path** — `ProviderBase.__init__` imports `TemplateEnv`
   (`base.py:66`) and `_prepare_` calls `self._tpl.get_template()`
   (`base.py:142`). That contract must be byte-identical to 1.5.7, because
   eight provider call sites render email bodies through the `Template` object
   it returns.

---

## Scope

Add the four integration tests from spec §4:

- `test_template_env_lazy_not_built_on_import` — patch
  `TemplateParser.__init__` with a counter, import `notify.notify` fresh, assert
  zero constructions.
- `test_template_env_memoised` — two accesses return the same object.
- `test_import_notify_without_templates_dir` — with `TEMPLATE_DIR` pointing at a
  nonexistent path, `import notify` succeeds and warns.
- `test_provider_base_get_template_still_works` — a minimal `ProviderBase`
  subclass resolves a template through `self._tpl.get_template()` exactly as
  before.

Place them in `tests/test_templates_integration.py` (or append to
`tests/test_templates.py` if the fixtures make that cleaner — decide and record
the choice).

**NOT in scope**: unit tests for `TemplateParser` (TASK-012); any production-code
change; testing actual email delivery through any provider; fixing the
pre-existing sync-render-inside-a-running-loop hazard (spec §7 R4).

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `tests/test_templates_integration.py` | CREATE | Lazy singleton + provider path integration tests |

---

## Codebase Contract (Anti-Hallucination)

### Verified Imports

```python
import importlib
import sys
import pytest
from notify.templates import TemplateParser
import notify.notify as nn
from notify.providers.base import ProviderBase
```

### Existing Signatures to Use

```python
# notify/providers/base.py:64-72 — the seam under test
try:
    from notify.notify import TemplateEnv   # line 66
    self._tpl = TemplateEnv                 # line 67
    self._template = None                   # line 68
except Exception as err:
    raise RuntimeError(
        f"Notify: Can't load the Jinja2 Template Parser: {err}"
    ) from err

# notify/providers/base.py:116-145
async def _prepare_(self, recipient: Actor = None, message=None,
                    template: str = None, **kwargs):
    ...
    if template:
        self._template = self._tpl.get_template(template)   # line 142
    else:
        self._template = None
    return msg

# notify/providers/base.py — abstract methods a test subclass MUST implement:
@abstractmethod
async def connect(self, *args, **kwargs): ...   # line 94-96
@abstractmethod
async def close(self): ...                      # line 98-100
@abstractmethod
async def _send_(self, to, message, subject=None, **kwargs): ...  # line 187-190

# ProviderBase declares: provider, provider_type, blocking (see CLAUDE.md)
```

```python
# notify/conf.py:6-10 — TEMPLATE_DIR, monkeypatch target for the missing-dir test
if not (template_dir := config.get('TEMPLATE_DIR')):
    TEMPLATE_DIR = BASE_DIR.joinpath("templates")
else:
    TEMPLATE_DIR = Path(template_dir).resolve()
```

### Post-refactor surface under test

```python
# notify/notify.py — after TASK-010
_TEMPLATE_ENV: Optional[TemplateParser] = None
def __getattr__(name: str): ...   # PEP 562 — builds TemplateEnv on first access
def __dir__() -> list[str]: ...
# NOTE: `TemplateEnv = None` at old line 10 is GONE. `"TemplateEnv" in vars(nn)`
#       must be False until first access.
```

### Does NOT Exist

- ~~`tests/integration/`~~ — the suite is FLAT; existing tests sit directly in
  `tests/`. Do not create a subdirectory.
- ~~A concrete instantiable provider suitable as a test double~~ — every
  provider in `notify/providers/` reaches for real credentials or transports.
  Define a minimal local `ProviderBase` subclass in the test module instead.
- ~~`notify.notify.get_template_env()`~~ — TASK-010 exposes the lazy value
  through `__getattr__` on the name `TemplateEnv`, not a new function. Verify
  what TASK-010 actually shipped before writing assertions.
- ~~`Notify()` factory usage in these tests~~ — `Notify.__new__` dynamically
  imports a real provider module (`notify/notify.py:64-80`) and will fail
  without credentials. Test `ProviderBase` directly.
- ~~Network access~~ — offline only.

---

## Implementation Notes

### Pattern to Follow

```python
def test_template_env_lazy_not_built_on_import(monkeypatch):
    """Importing notify.notify must not construct a TemplateParser (spec §7 R5)."""
    calls = []
    original = TemplateParser.__init__

    def counting_init(self, *args, **kwargs):
        calls.append(1)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(TemplateParser, "__init__", counting_init)
    for mod in [m for m in sys.modules if m.startswith("notify")]:
        sys.modules.pop(mod, None)

    importlib.import_module("notify.notify")
    assert calls == []            # nothing built at import time
```

```python
class _DummyProvider(ProviderBase):
    """Minimal concrete provider — no transport, no credentials."""
    provider = "dummy"
    blocking = False

    async def connect(self, *args, **kwargs): ...
    async def close(self): ...
    async def _send_(self, to, message, subject=None, **kwargs): return message
```

### Key Constraints

- **Module reloading is the sharp edge here.** Popping `notify*` out of
  `sys.modules` affects other tests in the same session. Use `monkeypatch` and
  restore state, or mark these tests to run in isolation. Verify the full suite
  still passes *in both orders* (`pytest tests/` and `pytest tests/ -p no:randomly`
  if applicable) before declaring done.
- `pytest-xdist` is available (`pyproject.toml:110`); if module-reload tests
  prove flaky under `-n auto`, note it in the Completion Note rather than
  silently weakening the assertions.
- `filterwarnings = ["error"]` is active (`pyproject.toml:156`) — the
  missing-directory path logs via `logger.warning` (fine), but if TASK-010 used
  `warnings.warn` anywhere, wrap it in `pytest.warns`.
- **Do not modify production code.** Report failures against TASK-010.
- `_DummyProvider` must satisfy every `@abstractmethod` on `ProviderBase`
  (`connect`, `close`, `_send_`) or instantiation raises `TypeError`.

### References in Codebase

- `notify/providers/base.py:38-80` — `ProviderBase.__init__`, for building the
  minimal subclass correctly.
- `notify/providers/base.py:116-145` — `_prepare_`, the method under test.
- `tests/test_email_utf8.py` — house style for offline provider-adjacent tests.

---

## Acceptance Criteria

- [ ] `tests/test_templates_integration.py` implements all four integration tests from spec §4
- [ ] `.venv/bin/python -m pytest tests/test_templates_integration.py -v` passes
- [ ] `.venv/bin/python -m pytest tests/ -v` passes with no NEW failures versus the pre-refactor baseline
- [ ] The full suite passes when `tests/test_templates_integration.py` runs both first and last
- [ ] `import notify` succeeds with `TEMPLATE_DIR` pointing at a nonexistent path
- [ ] Importing `notify.notify` constructs zero `TemplateParser` instances
- [ ] Two `nn.TemplateEnv` accesses return the identical object
- [ ] A `ProviderBase` subclass resolves a template via `self._tpl.get_template()`
- [ ] `notify/providers/base.py` is UNCHANGED by this task
- [ ] No test performs network I/O
- [ ] `ruff check tests/test_templates_integration.py` clean

---

## Test Specification

This task *is* the test specification. See spec §4 "Integration Tests" for the
authoritative table.

---

## Agent Instructions

1. **Read the spec** — §4 "Integration Tests", §2 Integration Points, §7 R4/R5.
2. **Check dependencies** — TASK-010 and TASK-012 must both be in
   `sdd/tasks/completed/`.
3. **Verify the Codebase Contract** — read `notify/notify.py` post-TASK-010 and
   `notify/providers/base.py:38-145` before writing assertions.
4. **Update status** in `sdd/tasks/index/templateparser-refactor.json` → `in-progress`.
5. **Write the tests.** Do not modify production code.
6. **Verify** every acceptance criterion, including suite-ordering robustness.
7. **Move this file** to `sdd/tasks/completed/TASK-013-integration-tests-lazy-env.md`.
8. **Update index** → `done`.
9. **Fill in the Completion Note**, including where you placed the tests and any
   xdist flakiness observed.

Use `.venv/bin/python` directly — `.venv/bin/activate` is stale.

---

## Completion Note

*(Agent fills this in when done)*

**Completed by**: <session or agent ID>
**Date**: YYYY-MM-DD
**Notes**:

**Test placement decision**:

**Deviations from spec**: none | describe if any
