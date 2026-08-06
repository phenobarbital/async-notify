# TASK-017: Offline test suite for inline Jinja2 template source

**Feature**: FEAT-003 — Inline Jinja2 template source for `send()`
**Spec**: `sdd/specs/jinja-string-notify.spec.md`
**Status**: pending
**Priority**: high
**Estimated effort**: L (4-8h)
**Depends-on**: TASK-014, TASK-015, TASK-016
**Assigned-to**: unassigned

---

## Context

FEAT-003 makes two claims that are only worth anything if they are asserted
rather than assumed:

1. **G2 — it is provider-agnostic.** A change confined to
   `ProviderBase._prepare_` reaches every provider. The test for this is a
   concrete `ProviderBase` subclass exercising both render paths; if that
   passes, SMTP/Gmail/SES/Outlook/Office365/Teams/Telegram all work by
   construction, because they share the same `_prepare_` and the same
   `self._template` object.
2. **G4 — existing filename callers are untouched.** This is the risk that
   matters most (spec §7 R2): a heuristic false positive would not crash, it
   would silently render the *filename* as the message body. The parametrised
   filename test is the guard.

This task writes the whole offline suite in one file. No network, no SMTP, no
external services; template directories are built with `tmp_path`.

Implements spec §3 Module 4 and §4 in full.

---

## Scope

- Create `tests/test_jinja_string_templates.py`.
- Implement the fixtures from spec §4 ("Test Data / Fixtures"): `template_dir`,
  `parser`, `dummy_provider`.
- Implement **every** unit test in spec §4's unit table (28 rows) and **every**
  integration test in the integration table (7 rows), including the three model
  tests contributed by TASK-016.
- Group them into classes by subject (`TestIsTemplateSource`, `TestFromString`,
  `TestStringCache`, `TestPrepareDispatch`, `TestMessageModel`, `TestRenderPaths`).

**NOT in scope**:
- Changing any file under `notify/`. If a test fails, the bug belongs to
  TASK-014/015/016 — report it, do not patch production code from this task.
- Adding tests for FEAT-002 behaviour (`JinjaConfig`, `render_string`,
  `add_templates`, the `add_filter` bug, the `"NAV: "` prefix). Those belong to
  FEAT-002's TASK-012.
- Live/integration tests against real providers. Everything here is offline.
- Testing OneSignal (it never calls `_prepare_` — spec §7 R7).
- `docs/` or `README.md` — that is TASK-018.

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `tests/test_jinja_string_templates.py` | CREATE | The complete offline suite for FEAT-003 |

---

## Codebase Contract (Anti-Hallucination)

> **CRITICAL**: This section contains VERIFIED code references from the actual codebase.
> The implementing agent MUST use these exact imports, class names, and method signatures.
> **DO NOT** invent, guess, or assume any import, attribute, or method not listed here.

Verified 2026-08-06 against `dev@f42d302`.

### Verified Imports

```python
# stdlib / third-party
import pytest
from pathlib import Path
from unittest.mock import MagicMock
from jinja2 import Template

# From this repo — the surface under test
from notify.templates import (
    TemplateParser,            # notify/templates.py:13
    is_template_source,        # NEW — TASK-014
    JINJA_MARKERS,             # NEW — TASK-014
    DEFAULT_STRING_CACHE_SIZE, # NEW — TASK-014
)
from notify.providers.base import ProviderBase, ProviderType  # notify/providers/base.py
from notify.models import Message, BlockMessage               # notify/models.py:80, :108
from notify.models import Actor                               # notify/models.py
```

### Test-suite conventions in this repo

- `pytest.ini` sets `asyncio_mode = auto` — **async tests need no
  `@pytest.mark.asyncio` decorator.** Just `async def test_...`.
- Markers defined in `pytest.ini`: `integration`, `live`, `real_llm`. Everything
  in this task is offline, so **do not** apply any of them.
- Existing suite for reference style: `tests/test_email_utf8.py` (the FEAT-001
  offline regression suite — same shape: `tmp_path` fixtures, no network).
- Run with `.venv/bin/python -m pytest` — **not** `pytest` after
  `source .venv/bin/activate`; see "Does NOT Exist" below.

### Existing Signatures to Use

```python
# notify/templates.py
class TemplateParser:
    def __init__(self, directory: Path, filters: Optional[list] = None, **kwargs): ...  # line 20
        # NEW kwarg from TASK-014: string_cache_size: int = DEFAULT_STRING_CACHE_SIZE
    def get_template(self, filename: str): ...        # line 67 → FileNotFoundError if absent
    @property
    def environment(self): ...                        # lines 83-85 → the jinja2.Environment
    def add_filter(self, func, name=None) -> None: ...# line 87  ← NOTE: buggy when name is omitted
    # NEW from TASK-014:
    def from_string(self, source: str, *, cache: bool = True) -> Template: ...
    def clear_string_cache(self) -> None: ...
    _string_cache: OrderedDict[str, Template]
    _string_cache_size: int


# notify/providers/base.py
class ProviderType(Enum):                    # NOTIFY | SMS | EMAIL | PUSH | IM
class ProviderBase(ABC):
    provider: str = None
    provider_type: ProviderType = ProviderType.NOTIFY
    blocking: bool = True
    # abstract: connect(), close(), _send_()  ← a test subclass MUST implement all three
    def __init__(self, *args, **kwargs): ...            # line 47; sets self._tpl from TemplateEnv (line 66-67)
    async def _prepare_(self, recipient=None, message=None, template=None,
                        template_is_source=None, **kwargs): ...   # line 116 (+ TASK-015 param)
    def _render_sync_(self, to=None, message=None, subject=None, **kwargs): ...  # line 147
    async def _render_(self, to=None, message=None, subject=None, **kwargs): ... # line 167
    async def send(self, recipient=None, message=None, subject=None, **kwargs): ... # line 242


# notify/models.py
class Message(BaseModel):                    # line 80
    name: str; body: Union[str, dict]; content: str; sent: datetime
    template: Union[Path, str]               # line 93 — widened by TASK-016
class BlockMessage(Message): ...             # line 108
```

### Critical fixture detail — bypassing the singleton

`ProviderBase.__init__` binds `self._tpl` to the **module-level `TemplateEnv`
singleton** (`notify/providers/base.py:66-67`), which is built from
`TEMPLATE_DIR` at import time (`notify/notify.py:83-87`). Tests must **not**
depend on that directory existing. After constructing the test provider,
overwrite the attribute with a `tmp_path`-backed parser:

```python
    p = Dummy()
    p._tpl = TemplateParser(directory=template_dir)   # bypass TemplateEnv
```

### `_render_` / `_render_sync_` argument shape

Both build `self._templateargs` from a fixed set plus `**kwargs`
(`notify/providers/base.py:157-163` and `:177-183`):

```python
            self._templateargs = {
                "recipient": to,
                "username": to,
                "message": message,
                "subject": subject,
                **kwargs,
            }
```

So a string template under test can reference `{{ message }}`, `{{ subject }}`,
`{{ recipient }}`, `{{ username }}`, plus anything passed as an extra kwarg.
**`{{ content }}` is NOT available on the base class** — `mail.py:145-151` and
`ses.py:97-103` add `content`, the base does not.

### Does NOT Exist

- ~~`tests/test_jinja_string_templates.py`~~ — this task creates it. Current suite: `tests/test_email_utf8.py`, `tests/test_outlook.py`, `tests/test_outlook1.py`, `tests/test_ses.py`, `tests/sdd_scripts/`.
- ~~`tests/test_templates.py`~~ — does not exist; it is **FEAT-002's** file (its TASK-012). Do not create or write into it.
- ~~`tests/conftest.py`~~ — verify before assuming; if absent, define fixtures inside the test module.
- ~~`TemplateParser.render_string()`~~ — FEAT-002, not on `dev`. Do not test it here.
- ~~`ProviderBase._render_sync_` having any caller in the package~~ — verified none; the method exists at `base.py:147` and is invoked by no production code. Test it directly.
- ~~Template support in `Onesignal`~~ — `Onesignal.send()` (`notify/providers/onesignal/onesignal.py:93`) never calls `_prepare_`. Do not write a passing-template test for it.
- ~~`{{ content }}` in a base-class render~~ — see above; only `mail`/`ses` add it.
- ~~`.venv/bin/activate` as a usable activation script~~ — it carries a stale `VIRTUAL_ENV=/home/jesuslara/proyectos/navigator/notify/.venv`. Use `.venv/bin/python` directly, or recreate the venv with `uv venv`.

---

## Implementation Notes

### Pattern to Follow — the fixtures (spec §4)

```python
@pytest.fixture
def template_dir(tmp_path):
    """Minimal on-disk template set."""
    d = tmp_path / "templates"
    d.mkdir()
    (d / "hello.html").write_text("Hi {{ who }}", encoding="utf-8")
    return d


@pytest.fixture
def parser(template_dir):
    return TemplateParser(directory=template_dir)


@pytest.fixture
def dummy_provider(parser):
    """Concrete ProviderBase subclass wired to a tmp-dir parser.

    Proves the feature is provider-agnostic: nothing below ProviderBase is
    involved in the render path.
    """
    class Dummy(ProviderBase):
        provider = "dummy"
        provider_type = ProviderType.NOTIFY
        blocking = False

        async def connect(self, *args, **kwargs): ...
        async def close(self): ...
        async def _send_(self, to, message, subject=None, **kwargs):
            return await self._render_(to, message, subject, **kwargs)

    p = Dummy()
    p._tpl = parser          # bypass the module-level TemplateEnv singleton
    return p
```

### The two tests that carry the most weight

```python
    @pytest.mark.parametrize(
        "value",
        ["email.html", "welcome.txt", "notifications/welcome.html",
         "a_b-c.2.html", "template", ""],
    )
    def test_is_template_source_rejects_plain_filenames(self, value):
        """G4 guard (spec §7 R2).

        A false positive here would not crash — it would silently render the
        filename as the message body. That is the worst failure mode this
        feature can have, so this is the test that must never be relaxed.
        """
        assert is_template_source(value) is False


    async def test_string_and_file_template_render_identically(self, dummy_provider, template_dir):
        """The same body, on disk and inline, must produce identical output."""
        body = "Hi {{ who }}"
        await dummy_provider._prepare_(message="m", template="hello.html")
        from_file = await dummy_provider._render_(to=None, message="m", subject="s", who="x")
        await dummy_provider._prepare_(message="m", template=body)
        from_string = await dummy_provider._render_(to=None, message="m", subject="s", who="x")
        assert from_file == from_string
```

### Asserting "get_template was not called"

```python
        dummy_provider._tpl.get_template = MagicMock(
            side_effect=AssertionError("get_template must not be called for source")
        )
```

Cleaner than counting calls, and the failure message points straight at the bug.

### Key Constraints

- Offline only. No network, no SMTP, no real providers, no `TEMPLATE_DIR`
  dependency. Every directory comes from `tmp_path`.
- `asyncio_mode = auto` — write `async def test_...` with no decorator.
- One test = one behaviour. Do not fold the parametrised filename guard into a
  loop inside another test.
- Prefer `is` for identity assertions on cache hits (`a is b`), not `==` —
  `jinja2.Template` does not define `__eq__`, so `==` would silently pass on
  identity anyway and hide a cache miss on a future refactor.
- Docstring every test with the behaviour it pins, not a restatement of its name.
- If a test reveals a production bug, **stop and report it** in the Completion
  Note. Do not edit `notify/`.

### References in Codebase

- `tests/test_email_utf8.py` — the FEAT-001 offline suite; same conventions.
- `notify/providers/base.py:157-163`, `:177-183` — the `_templateargs` shape.
- `notify/providers/base.py:66-67` — why the fixture overwrites `_tpl`.

---

## Acceptance Criteria

- [ ] `tests/test_jinja_string_templates.py` exists and contains every unit test in spec §4's unit table (28 rows) and every integration test in its integration table (7 rows)
- [ ] `.venv/bin/python -m pytest tests/test_jinja_string_templates.py -v` — all pass
- [ ] `.venv/bin/python -m pytest tests/ -v` — full suite green, no new failures versus the pre-FEAT-003 baseline
- [ ] The suite runs with no network access and does not depend on `TEMPLATE_DIR` existing
- [ ] `test_is_template_source_rejects_plain_filenames` is parametrised over all six values and asserts `is False`
- [ ] `test_string_and_file_template_render_identically` passes
- [ ] Both `_render_()` (async) and `_render_sync_()` paths are covered with a string template
- [ ] The provider fixture is a real `ProviderBase` subclass, not a mock
- [ ] Cache tests assert object **identity** (`is`), eviction count, and LRU-order refresh
- [ ] `from_string` error tests assert `ValueError` (never `FileNotFoundError`) and check for `"Notify:"` in the message
- [ ] The three `Message` / `BlockMessage` model tests from TASK-016 are included
- [ ] **No file under `notify/` is modified by this task** — `git diff --name-only` shows only `tests/`
- [ ] No linting errors: `.venv/bin/python -m ruff check tests/test_jinja_string_templates.py`

---

## Test Specification

The authoritative list is spec §4. Structure the file as:

```python
class TestIsTemplateSource:      # 6 tests  — detection rules + the G4 guard
class TestFromString:            # 8 tests  — compile, render, env sharing, errors
class TestStringCache:           # 6 tests  — hit/miss, cache=False, LRU evict/refresh, clear
class TestPrepareDispatch:       # 8 tests  — the three-way dispatch in _prepare_
class TestMessageModel:          # 3 tests  — TASK-016 widening
class TestRenderPaths:           # 7 tests  — integration: async, sync, parity, kwarg forwarding,
                                 #            mail/ses send paths (transport mocked), singleton cache
```

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** at `sdd/specs/jinja-string-notify.spec.md` — §4 is the authoritative test list.
2. **Check dependencies** — TASK-014, TASK-015 and TASK-016 must all be in
   `sdd/tasks/completed/`. If TASK-016 was dropped from the feature, omit
   `TestMessageModel` and note it in the Completion Note.
3. **Verify the Codebase Contract** before writing ANY code:
   - Confirm `from_string`, `clear_string_cache`, `is_template_source` and the
     `template_is_source` parameter all exist as implemented.
   - Confirm `pytest.ini` still sets `asyncio_mode = auto`.
   - **NEVER** reference an import, attribute, or method not in the contract
     without verifying it exists.
4. **Update status** in `sdd/tasks/index/jinja-string-notify.json` → `"in-progress"`.
5. **Implement** the suite. Do not modify anything under `notify/`.
6. **Verify** every acceptance criterion.
7. **Move this file** to `sdd/tasks/completed/TASK-017-offline-test-suite.md`.
8. **Update index** → `"done"`.
9. **Fill in the Completion Note** below — including any production bug you
   found but did not fix.

---

## Completion Note

*(Agent fills this in when done)*

**Completed by**: <session or agent ID>
**Date**: YYYY-MM-DD
**Notes**: What was implemented, any deviations from scope, issues encountered.

**Deviations from spec**: none | describe if any
