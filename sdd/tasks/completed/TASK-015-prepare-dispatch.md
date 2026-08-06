# TASK-015: Three-way `template=` dispatch in `ProviderBase._prepare_`

**Feature**: FEAT-003 — Inline Jinja2 template source for `send()`
**Spec**: `sdd/specs/jinja-string-notify.spec.md`
**Status**: pending
**Priority**: high
**Estimated effort**: S (< 2h)
**Depends-on**: TASK-014
**Assigned-to**: unassigned

---

## Context

This is the task that makes FEAT-003 reach every provider. `_prepare_` is
defined **exactly once** in the entire package (`notify/providers/base.py:116`
— verified, no provider overrides it), and all eight render call sites operate
on the `jinja2.Template` object it stores in `self._template`, never on
`TemplateParser`. So replacing the five-line `if template:` block at
`base.py:140-144` propagates inline-source support to SMTP, Gmail, Office365,
Outlook, SES, mail, Telegram, Slack, Teams and Twilio with **zero per-provider
edits**.

This task is deliberately tiny and surgical. Its risk is not complexity — it is
that a mistake here silently changes behaviour for every existing caller.

Implements spec §3 Module 2. See spec §2 (dispatch diagram) and §7 R1/R2/R8/R9.

---

## Scope

- Add the parameter `template_is_source: Optional[bool] = None` to
  `ProviderBase._prepare_` (`notify/providers/base.py:116-122`), positioned
  immediately after `template` and before `**kwargs`.
- Replace the `if template:` block (`notify/providers/base.py:140-144`) with the
  three-way dispatch specified below.
- Add the `is_template_source` import from `notify.templates`.
- Extend the `_prepare_` docstring (Google-style) to document both `template`'s
  new dual meaning and `template_is_source`.

**NOT in scope**:
- Any change to `notify/templates.py` — that is TASK-014.
- Any change to `notify/models.py` — that is TASK-016.
- **Any change to any file under `notify/providers/*/`.** The whole point of
  this task is that none is needed. An acceptance criterion asserts it.
- Any change to `_render_`, `_render_sync_`, `_send_`, `__sent__` or `send()`.
- Making `Onesignal` support templates (it never calls `_prepare_` — spec §7 R7).
- Popping `template` / `template_is_source` out of the kwargs forwarded to
  `_send_` (spec §7 R8 — pre-existing, deliberately left alone).
- Reading a provider-level `self.template_is_source` attribute (spec §7 R9 —
  explicitly forbidden).

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `notify/providers/base.py` | MODIFY | Add `is_template_source` import; add `template_is_source` param to `_prepare_`; replace the dispatch at lines 140-144 |

---

## Codebase Contract (Anti-Hallucination)

> **CRITICAL**: This section contains VERIFIED code references from the actual codebase.
> The implementing agent MUST use these exact imports, class names, and method signatures.
> **DO NOT** invent, guess, or assume any import, attribute, or method not listed here.

Verified 2026-08-06 against `dev@f42d302`.

### Verified Imports

```python
# Already present at the top of notify/providers/base.py
import asyncio
from abc import ABC, abstractmethod
from typing import Any, Union, Optional
from collections.abc import Awaitable, Callable
from enum import Enum
from functools import partial
from concurrent.futures import ThreadPoolExecutor
from navconfig import DEBUG
from navconfig.logging import logging
from notify.types import SafeDict
from notify.exceptions import ProviderError
from notify.models import Actor
from .message import ThreadMessage

# NEW import this task must add — provided by TASK-014
from notify.templates import is_template_source
```

`Optional` is **already imported** (`typing`, top of file) — do not re-import it.

**Import placement**: `notify/providers/base.py` already imports
`from notify.models import Actor` at module level, and `notify.templates` has no
import-time side effects beyond building the module constants, so a module-level
`from notify.templates import is_template_source` is safe. Note the contrast
with `from notify.notify import TemplateEnv`, which is deliberately deferred
inside `__init__` (`base.py:66`) to dodge a circular import — **do not** move
that one, and do not put `is_template_source` inside the function body to
"match" it.

### Existing Signatures to Use

```python
# notify/providers/base.py
class ProviderBase(ABC):
    def __init__(self, *args, **kwargs):
        from notify.notify import TemplateEnv     # line 66 (deferred, inside a try)
        self._tpl = TemplateEnv                   # line 67  ← a TemplateParser instance
        self._template = None                     # line 68
        self.sent = kwargs.pop('sent', None)      # line 74
        for arg, val in kwargs.items():           # lines 76-80
            object.__setattr__(self, arg, val)    # ← see R9 below

    async def _prepare_(                          # line 116 ← THE ONLY DEFINITION
        self,
        recipient: Actor = None,                  # line 118
        message: Union[str, Any] = None,          # line 119
        template: str = None,                     # line 120
        **kwargs,                                 # line 121
    ):  # pylint: disable=W0613                   # line 122
        """..."""                                 # lines 123-127
        if self._kwargs:                          # line 128
            try:
                msg = message.format_map(SafeDict(recipient=recipient, **self._kwargs))
            except (AttributeError, ValueError):
                msg = message
        else:
            msg = message                         # line 139
        if template:                              # line 140  ← REPLACE lines 140-144
            # Getting Template from Template Parser.
            self._template = self._tpl.get_template(template)   # line 142
        else:
            self._template = None                 # line 144
        return msg                                # line 145
```

`self._tpl` is a `TemplateParser` (`notify/templates.py:13`). After TASK-014 it
exposes both `get_template(filename)` (`templates.py:67`) and
`from_string(source, *, cache=True)`.

### Callers of `_prepare_` — all inherit this change for free

Verified via `grep -rn '_prepare_' notify/`:

| File | Line | Call |
|---|---|---|
| `notify/providers/base.py` | 255-259 | `await self._prepare_(recipient=..., message=..., **kwargs)` |
| `notify/providers/mail.py` | 232-236 | same shape |
| `notify/providers/ses/ses.py` | 171-175 | same shape |

All three forward `**kwargs`, so `template=` and `template_is_source=` reach
`_prepare_` untouched. `notify/server/wrapper.py:70-78` forwards
`**self.kwargs` into `send()`, so the Redis path works with no change either.

### Consumers of `self._template` — ALL UNCHANGED by this task

| File | Line | Call |
|---|---|---|
| `notify/providers/base.py` | 164 | `self._template.render(...)` |
| `notify/providers/base.py` | 184 | `await self._template.render_async(...)` |
| `notify/providers/smtp/smtp.py` | 189 | `self._template.render(...)` |
| `notify/providers/mail.py` | 152 | `await self._template.render_async(...)` |
| `notify/providers/ses/ses.py` | 104 | `await self._template.render_async(...)` |
| `notify/providers/gmail/gmail.py` | 84 | `await self._template.render_async(...)` |
| `notify/providers/outlook/outlook.py` | 146 | `await self._template.render_async(...)` |
| `notify/providers/office365/office365.py` | 166 | `await self._template.render_async(...)` |

All eight call methods on the **`jinja2.Template` object**, which is why
`from_string()` must return a `Template` and not a rendered string.

### Does NOT Exist

- ~~A per-provider `_prepare_` override~~ — verified: `grep -rn "def _prepare_" notify/` returns exactly one hit, `base.py:116`. **Do not add one.**
- ~~`template_string=` as a `send()` keyword~~ — explicitly rejected (spec §1 Non-Goals, §9 Q1). Overload `template=` instead.
- ~~`TemplateSource` wrapper class~~ — considered and rejected (spec §9 Q1).
- ~~`self._tpl.render_string()`~~ — does not exist on `dev`; belongs to FEAT-002 and returns a `str`, not a `Template`. Do not call it.
- ~~`self.template_is_source` as a provider-level default~~ — `ProviderBase.__init__` *will* set such an attribute if a caller passes it to the constructor (`base.py:76-80`), but `_prepare_` must read **only its parameter**. Do NOT add a `getattr(self, "template_is_source", None)` fallback (spec §7 R9).
- ~~Template support in OneSignal~~ — `Onesignal.send()` (`notify/providers/onesignal/onesignal.py:93`) never calls `_prepare_`; `grep -n "_template" notify/providers/onesignal/onesignal.py` returns nothing. Out of scope.

---

## Implementation Notes

### Pattern to Follow

Replace `notify/providers/base.py:140-144` with exactly this shape:

```python
        if template:
            if template_is_source is None:
                use_source = is_template_source(template)
            else:
                use_source = bool(template_is_source)
            if use_source:
                # Compiling caller-supplied Jinja2 source.
                self._template = self._tpl.from_string(template)
            else:
                # Getting Template from Template Parser.
                self._template = self._tpl.get_template(template)
        else:
            self._template = None
        return msg
```

And the signature:

```python
    async def _prepare_(
        self,
        recipient: Actor = None,
        message: Union[str, Any] = None,
        template: Optional[str] = None,
        template_is_source: Optional[bool] = None,
        **kwargs,
    ):  # pylint: disable=W0613
```

### Key Constraints

- **`template=None` and `template=""` must still yield `self._template = None`.**
  The outer `if template:` truthiness check is unchanged — keep it exactly as is.
- **`template_is_source=False` must reproduce 1.5.7 semantics byte for byte**,
  including raising `FileNotFoundError` for a missing file.
- **Three states, not two.** `None` (auto-detect) is distinct from `False`
  (force filename). Do NOT write `if template_is_source:` — that collapses
  `None` and `False` and silently disables auto-detection.
- Do not touch the `message.format_map(SafeDict(...))` block at lines 128-139.
- Keep the `# pylint: disable=W0613` comment on the signature.
- Google-style docstring with strict type hints (CLAUDE.md → Code Standards).

### Docstring content (required)

```
        Args:
            recipient: Target Actor (used for ``format_map`` interpolation).
            message: Raw message body.
            template: Either a template **filename** resolved through
                ``TEMPLATE_DIR``, or raw Jinja2 **source text**. The two are
                discriminated by :func:`notify.templates.is_template_source`
                unless *template_is_source* forces the choice.
            template_is_source: ``None`` (default) auto-detects; ``True``
                forces *template* to be compiled as source; ``False`` forces
                filesystem resolution, i.e. exact 1.5.7 semantics.
```

### References in Codebase

- `notify/providers/base.py:140-144` — the exact block being replaced.
- `notify/providers/base.py:184` — proves `self._template` must stay a `Template`.
- `notify/templates.py` — `is_template_source()` and `from_string()` from TASK-014.

---

## Acceptance Criteria

- [ ] `_prepare_(template="{{ who }}")` sets `self._template` to a compiled template and **never calls** `get_template` (patch it and assert)
- [ ] `_prepare_(template="hello.html")` routes to `get_template("hello.html")` exactly as in 1.5.7 (patch and assert the call arg)
- [ ] `_prepare_()` with no `template` → `self._template is None`
- [ ] `_prepare_(template="")` → `self._template is None`
- [ ] `_prepare_(template="Hello world", template_is_source=True)` compiles as source and does not hit the filesystem
- [ ] `_prepare_(template="{{ x }}", template_is_source=False)` routes to `get_template()` and raises `FileNotFoundError`
- [ ] A filename-shaped value that does not exist still raises `FileNotFoundError`
- [ ] Malformed source surfaces TASK-014's `ValueError`, not a `FileNotFoundError`
- [ ] `send(..., template=..., template_is_source=True)` reaches `_prepare_` through `**kwargs` on the base `send()`
- [ ] **`git diff --name-only` shows `notify/providers/base.py` and no other file under `notify/providers/`**
- [ ] `grep -rn "def _prepare_" notify/` still returns exactly one hit
- [ ] No linting errors: `.venv/bin/python -m ruff check notify/providers/base.py`
- [ ] Existing suite still green: `.venv/bin/python -m pytest tests/ -v`

---

## Test Specification

> Formal tests land in TASK-017. Use this scaffold to self-verify before handing off.

```python
import pytest
from unittest.mock import MagicMock
from notify.providers.base import ProviderBase, ProviderType
from notify.templates import TemplateParser


@pytest.fixture
def provider(tmp_path):
    d = tmp_path / "templates"; d.mkdir()
    (d / "hello.html").write_text("Hi {{ who }}", encoding="utf-8")

    class Dummy(ProviderBase):
        provider = "dummy"
        provider_type = ProviderType.NOTIFY
        blocking = False
        async def connect(self, *a, **kw): ...
        async def close(self): ...
        async def _send_(self, to, message, subject=None, **kw): return message

    p = Dummy()
    p._tpl = TemplateParser(directory=d)   # bypass the TemplateEnv singleton
    return p


class TestPrepareDispatch:
    async def test_source_bypasses_get_template(self, provider):
        provider._tpl.get_template = MagicMock(side_effect=AssertionError("must not be called"))
        await provider._prepare_(message="m", template="Hi {{ who }}")
        assert provider._template.render(who="x") == "Hi x"

    async def test_filename_unchanged(self, provider):
        await provider._prepare_(message="m", template="hello.html")
        assert provider._template.render(who="x") == "Hi x"

    async def test_no_template_is_none(self, provider):
        await provider._prepare_(message="m")
        assert provider._template is None

    async def test_empty_template_is_none(self, provider):
        await provider._prepare_(message="m", template="")
        assert provider._template is None

    async def test_force_source_true(self, provider):
        await provider._prepare_(message="m", template="Hello world", template_is_source=True)
        assert provider._template.render() == "Hello world"

    async def test_force_source_false(self, provider):
        with pytest.raises(FileNotFoundError):
            await provider._prepare_(message="m", template="{{ x }}", template_is_source=False)
```

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** at `sdd/specs/jinja-string-notify.spec.md` — §2, §3 Module 2, §7 R1/R2/R8/R9.
2. **Check dependencies** — TASK-014 must be in `sdd/tasks/completed/`. This task
   cannot compile without `is_template_source` and `from_string`.
3. **Verify the Codebase Contract** before writing ANY code:
   - Re-read `notify/providers/base.py:116-145` and confirm the block still matches.
   - Confirm `grep -rn "def _prepare_" notify/` still returns exactly one hit.
   - **NEVER** reference an import, attribute, or method not in the contract
     without verifying it exists.
4. **Update status** in `sdd/tasks/index/jinja-string-notify.json` → `"in-progress"`.
5. **Implement** following the scope, contract, and notes above.
6. **Verify** every acceptance criterion — especially the "no other provider
   file modified" one.
7. **Move this file** to `sdd/tasks/completed/TASK-015-prepare-dispatch.md`.
8. **Update index** → `"done"`.
9. **Fill in the Completion Note** below.

---

## Completion Note

**Completed by**: sdd-worker (Claude)
**Date**: 2026-08-06
**Notes**: Added `from notify.templates import is_template_source` at module
level in `notify/providers/base.py` and replaced the `if template:` block
(lines 140-144) with the three-way dispatch from spec §2/§3 Module 2. Added
`template_is_source: Optional[bool] = None` immediately after `template`
and before `**kwargs`, widened `template` to `Optional[str]`, kept the
`# pylint: disable=W0613` comment, and extended the docstring to
Google-style covering both new args. `message.format_map(SafeDict(...))`
block untouched. Verified by hand (no `pytest-asyncio` harness available
standalone, so exercised via a `Dummy(ProviderBase)` fixture identical to
the task's Test Specification, run through `asyncio.run`): source bypasses
`get_template` (patched to raise if called), filename routes through
`get_template` unchanged, `None`/`""` template → `self._template is None`,
`template_is_source=True` forces source compilation, `template_is_source=False`
forces filesystem lookup and raises `FileNotFoundError`, a missing-file
filename still raises `FileNotFoundError`, and malformed source surfaces
TASK-014's `ValueError` (never `FileNotFoundError`). `git diff --name-only`
confirms only `notify/providers/base.py` changed; `grep -rn "def _prepare_" notify/`
still returns exactly one hit. `ruff check notify/providers/base.py`: only
the pre-existing `I001` (import sort) and `F401` (unused `ProviderError`)
findings remain, both confirmed present on baseline `dev` before this
change — left untouched, out of scope. Full suite `pytest tests/ -v`: 59
passed, 2 failed, 3 errors — identical to baseline `dev` (pre-existing,
unrelated AWS region / event-loop fixture issues).

**Deviations from spec**: none.
