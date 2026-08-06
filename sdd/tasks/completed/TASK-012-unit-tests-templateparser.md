# TASK-012: Unit tests for the refactored TemplateParser

**Feature**: FEAT-002 — TemplateParser refactor (homologation with ai-parrot TemplateEngine)
**Spec**: `sdd/specs/templateparser-refactor.spec.md`
**Status**: pending
**Priority**: high
**Estimated effort**: L (4-8h)
**Depends-on**: TASK-009
**Assigned-to**: unassigned

---

## Context

Implements the unit-test half of **Module 6** (spec §3, §4). `notify/templates.py`
has **no test coverage at all** today — the existing suite is
`tests/test_email_utf8.py`, `test_outlook.py`, `test_outlook1.py`,
`test_ses.py` plus `tests/sdd_scripts/`. This task creates
`tests/test_templates.py` and covers the 30 unit tests enumerated in spec §4.

The highest-value tests here are the **backward-compatibility guards**: they are
what prove the refactor did not silently change rendered email output. Three in
particular encode spec §7 risks R1, R2 and R7.

---

## Scope

Create `tests/test_templates.py` implementing every unit test in spec §4:

**Construction & configuration (TASK-007 surface)**
- `test_init_legacy_directory_path`, `test_init_accepts_str_directory`
- `test_init_missing_dir_warns_not_raises`
- `test_init_does_not_write_compiled_artifact`
- `test_config_dict_legacy_merge`
- `test_config_instance_not_mutated` — guards spec §7 R7
- `test_template_debug_does_not_leak`
- `test_optional_extension_missing_is_tolerated`
- `test_multiple_template_dirs_precedence`
- `test_autoescape_off_by_default` — guards spec §7 R2
- `test_autoescape_opt_in`
- `test_undefined_permissive_by_default`, `test_strict_undefined_opt_in`
- `test_whitespace_defaults_unchanged` — guards spec §7 R1

**Public API (TASK-008 surface)**
- `test_add_template_dir_runtime`
- `test_add_templates_in_memory`, `test_in_memory_shadows_filesystem`
- `test_render_sync_backward_compat`, `test_render_async_backward_compat`
- `test_render_string_sync_and_async`
- `test_add_globals`, `test_add_filters_mapping`
- `test_get_template_missing_raises_filenotfound`
- `test_environment_property`
- `test_compile_directory_explicit`, `test_bytecode_cache_opt_in`

**Defect regressions (TASK-009 surface)**
- `test_add_filter_without_name_uses_func_name` — **the regression test for the
  `templates.py:94` bug**
- `test_add_filter_with_explicit_name`
- `test_add_filter_non_callable_raises_typeerror`
- `test_error_prefix_is_notify`

**NOT in scope**: integration tests for the lazy singleton and the provider
path (TASK-013); any production-code change — if a test fails, the fix belongs
to the owning task, not here.

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `tests/test_templates.py` | CREATE | Full unit suite for `TemplateParser` |

---

## Codebase Contract (Anti-Hallucination)

### Verified Imports

```python
import pytest
from pathlib import Path
from notify.templates import TemplateParser, JinjaConfig, jinja_config
from jinja2 import Environment, StrictUndefined, Undefined
```

### Existing Test Conventions

```python
# pyproject.toml:153-158 — pytest is configured STRICTLY. Read this before writing.
[tool.pytest.ini_options]
addopts = ["--strict-config", "--strict-markers"]
filterwarnings = [
  "error",     # ← WARNINGS ARE ERRORS. See Key Constraints below.
  "ignore:The loop argument is deprecated since Python 3\\.8, ...",
]

# Available plugins (pyproject.toml:106-112):
#   pytest>=8.0.0, pytest-asyncio>=0.24.0, pytest-cov>=6.0.0,
#   pytest-cython>=0.3.1, pytest-xdist>=3.6.1, pytest-assume>=2.4.3
```

```python
# tests/test_email_utf8.py — read it for the house style (fixtures, naming,
# offline-only discipline). It is the most recent test module in the repo.
```

### Post-refactor signatures under test

```python
class TemplateParser:
    def __init__(self, directory=None, filters=None, *, template_dirs=None,
                 globals_=None, config=None, bytecode_cache_dir=None,
                 autoescape=None, strict_undefined=False,
                 strict_directory=False, **kwargs): ...
    def get_template(self, filename: str): ...
    @property
    def environment(self) -> Environment: ...
    def add_filter(self, func, name=None) -> None: ...
    def add_filters(self, filters) -> None: ...
    def add_globals(self, globals_) -> None: ...
    def add_templates(self, templates) -> None: ...
    def add_template_dir(self, path) -> None: ...
    def render(self, filename, params=None) -> str: ...          # SYNC
    async def render_async(self, filename, params=None) -> str: ...
    def render_string(self, source, params=None) -> str: ...      # SYNC
    async def render_string_async(self, source, params=None) -> str: ...
    def compile_directory(self, target, *, zip="deflated") -> None: ...
```

### Does NOT Exist

- ~~`tests/unit/` or `tests/integration/` directories~~ — the suite is FLAT.
  Existing files sit directly in `tests/`. Create `tests/test_templates.py`,
  not `tests/unit/test_templates.py`. (Spec §5 mentions
  `pytest tests/unit/` from the template boilerplate — the flat layout wins.)
- ~~`tests/conftest.py`~~ — verify with `ls tests/conftest.py`; if absent and you
  need shared fixtures, create it, but prefer module-local fixtures.
- ~~A pytest `asyncio_mode` setting~~ — `[tool.pytest.ini_options]` does not set
  one, so `pytest-asyncio` defaults to strict mode: every async test needs an
  explicit `@pytest.mark.asyncio` decorator. Verify before writing async tests.
- ~~Network access in tests~~ — the suite must run fully offline.
- ~~`TemplateParser.render()` as a coroutine~~ — it is synchronous. Do not
  `await` it.

---

## Implementation Notes

### Pattern to Follow

```python
@pytest.fixture
def template_dir(tmp_path):
    """Minimal on-disk template set."""
    d = tmp_path / "templates"
    d.mkdir()
    (d / "hello.html").write_text("Hello {{ name }}!", encoding="utf-8")
    (d / "raw.html").write_text("{{ value }}", encoding="utf-8")
    return d


@pytest.fixture
def parser(template_dir):
    return TemplateParser(directory=template_dir)


def test_config_instance_not_mutated(template_dir):
    """A shared JinjaConfig must not accumulate directories (spec §7 R7)."""
    cfg = JinjaConfig()
    TemplateParser(directory=template_dir, config=cfg)
    TemplateParser(directory=template_dir, config=cfg)
    assert cfg.template_dirs == []
```

### Key Constraints

- **`filterwarnings = ["error"]` is active** (`pyproject.toml:156`). Tests that
  exercise the tolerant-extension path or the missing-directory path will emit
  warnings via `logger.warning`, which is *logging*, not `warnings.warn` — those
  are fine. But if any production code calls `warnings.warn` (e.g. a
  `DeprecationWarning` on `jinja_config`), the test MUST wrap it in
  `pytest.warns(...)` or the suite fails.
- **Offline only.** No network, no SMTP, no real providers. Use `tmp_path`
  for every directory.
- **Do not modify production code.** If a test exposes a genuine bug, record it
  in the Completion Note and raise it against the owning task
  (TASK-007/008/009) rather than patching `notify/templates.py` here.
- `test_template_debug_does_not_leak` needs to manipulate the navconfig
  `TEMPLATE_DEBUG` value — use `monkeypatch` against
  `notify.templates.config.getboolean`, not a real env file.
- `test_optional_extension_missing_is_tolerated` should simulate absence by
  monkeypatching `importlib.import_module` to raise `ImportError` for the
  target module, since the packages are genuinely not installed anyway.
- Assert on *rendered output*, not on internals, wherever possible — that is
  what proves backward compatibility.

### References in Codebase

- `tests/test_email_utf8.py` — house style for a recent, offline, provider-adjacent suite.
- `pyproject.toml:153-158` — pytest configuration.
- Spec §4 — the authoritative table of the 30 tests.

---

## Acceptance Criteria

- [ ] `tests/test_templates.py` exists and implements every unit test in spec §4
- [ ] `.venv/bin/python -m pytest tests/test_templates.py -v` passes with 0 failures
- [ ] `.venv/bin/python -m pytest tests/ -v` shows no NEW failures versus the pre-refactor baseline
- [ ] `test_add_filter_without_name_uses_func_name` fails against the unfixed `templates.py:94` and passes after TASK-009 (verify by temporarily reverting, then restore)
- [ ] `test_autoescape_off_by_default`, `test_whitespace_defaults_unchanged` and `test_config_instance_not_mutated` are present and green
- [ ] No test performs network I/O
- [ ] Every directory used is created under `tmp_path`
- [ ] `ruff check tests/test_templates.py` clean
- [ ] Async tests are correctly marked for `pytest-asyncio` strict mode

---

## Test Specification

This task *is* the test specification. See spec §4 for the authoritative table
of 30 unit tests and their descriptions.

---

## Agent Instructions

1. **Read the spec** — §4 (the full test table), §7 (risks R1, R2, R7 — three
   tests exist specifically to guard them).
2. **Check dependencies** — TASK-009 must be in `sdd/tasks/completed/`, which
   transitively means TASK-007 and TASK-008 are done too.
3. **Verify the Codebase Contract** — read `notify/templates.py` in its
   post-refactor state and `pyproject.toml:153-158` before writing tests.
4. **Update status** in `sdd/tasks/index/templateparser-refactor.json` → `in-progress`.
5. **Write the tests.** Do not modify production code.
6. **Verify** every acceptance criterion.
7. **Move this file** to `sdd/tasks/completed/TASK-012-unit-tests-templateparser.md`.
8. **Update index** → `done`.
9. **Fill in the Completion Note**, listing any bug the tests exposed.

Use `.venv/bin/python` directly — `.venv/bin/activate` is stale.

---

## Completion Note

**Completed by**: sdd-worker (Claude)
**Date**: 2026-08-06
**Notes**: Created `tests/test_templates.py` implementing all 30 unit
tests from spec §4, plus one extra (`test_compile_directory_noop_
without_directories`) covering the documented "no-op with no
directories" behaviour from TASK-008's acceptance criteria that wasn't
given its own named row in the spec table. Corrected a stale Codebase
Contract assumption before writing tests: the contract claimed no
`asyncio_mode` was set, but a root-level `pytest.ini` (which takes
precedence over `[tool.pytest.ini_options]` in `pyproject.toml` — pytest
uses exactly one ini source) sets `asyncio_mode = auto`, confirmed via
`pytest`'s own `configfile:` banner ("ignoring pytest config in
pyproject.toml!"). Async tests are therefore plain `async def` without
needing an explicit `@pytest.mark.asyncio` marker.

Ran into spec §7 R4 (pre-existing, explicitly out of scope) directly:
with `enable_async=True`, Jinja2's synchronous `render()`/`render_string()`
drive the async code path via an internal `asyncio.run()`, which raises
`RuntimeError: asyncio.run() cannot be called from a running event loop`
if called from inside an already-running loop (i.e. from inside an
`async def` pytest-asyncio test). `test_render_async_backward_compat` and
`test_render_string_sync_and_async` originally mixed sync + async calls
inside `async def` tests and hit this exactly. Fixed by keeping both as
plain synchronous test functions that drive the async variant explicitly
via `asyncio.run()` — never nesting event loops — rather than touching
production code to "fix" R4, which is explicitly out of scope per the
spec. `test_error_prefix_is_notify` calls only the async path and was
unaffected.

Manually verified the regression premise for
`test_add_filter_without_name_uses_func_name`: reproduced the exact
pre-TASK-009 `add_filter` body (`name.__name__` bug) via a monkeypatched
bound method and confirmed it raises `AttributeError: 'NoneType' object
has no attribute '__name__'` — i.e. this test would fail against the
unfixed code and passes against the current (TASK-009-fixed)
implementation.

`tests/test_templates.py -v`: 31 passed. Full `pytest tests/ -v`: 90
passed (59 pre-existing + 31 new), 2 failed + 3 errors — identical
pre-existing `dev`-baseline failures (AWS SES mock region, Outlook
event-loop fixture), no new regressions. `ruff check
tests/test_templates.py` clean. No network I/O; every directory is
created under `tmp_path`.

**Bugs exposed (raised against which task)**: none — no genuine
production bug was found; TASK-007/008/009 all held up under test.

**Deviations from spec**: (1) one extra test beyond the 30 listed
(`test_compile_directory_noop_without_directories`), covering an
already-specified acceptance criterion. (2) `test_render_async_backward_
compat` and `test_render_string_sync_and_async` are plain `def` tests
rather than `async def`, to avoid triggering the pre-existing, explicitly
out-of-scope R4 nested-event-loop hazard — behaviour under test is
unchanged, only the test's own execution context.
