# TASK-016: Widen `Message.template` from `Path` to `Union[Path, str]`

**Feature**: FEAT-003 — Inline Jinja2 template source for `send()`
**Spec**: `sdd/specs/jinja-string-notify.spec.md`
**Status**: pending
**Priority**: medium
**Estimated effort**: S (< 2h)
**Depends-on**: none
**Assigned-to**: unassigned

---

## Context

`notify/models.py:93` declares `template: Path` on the `Message` datamodel, so
the model can only ever carry a template **filename**. Once `send()` accepts
inline Jinja2 source (TASK-014 + TASK-015), that field type is inconsistent with
the rest of the library.

This implements spec §9 Q5, resolved by the author at approval time: **yes,
widen it**. It was originally listed as a non-goal; the approval flipped it, and
spec §1 G8 now carries the decision.

The change is one line. It is a separate task because it shares **no file** with
any other task in this feature, and because it is the one piece of FEAT-003 that
is independently droppable — spec §8 records that if the "widen it later rather
than now" reading turns out to be the intended one, this task and its three
tests can be deleted without touching anything else.

Implements spec §3 Module 3.

---

## Scope

- Change `template: Path` to `template: Union[Path, str]` at `notify/models.py:93`.

**NOT in scope**:
- Any other line of `notify/models.py`. Do not add `Field(...)` to the field, do
  not reorder fields, do not touch `Account`, `Actor`, `Chat`, `Channel`,
  `Attachment`, `BlockMessage`, `MailAttachment`, `MailMessage`, or the Teams
  card family.
- Wiring `Message` / `BlockMessage` / `MailMessage` into the send path. They
  have **no consumers inside `notify/`** and this task does not change that
  (spec §1 Non-Goals).
- Adding validation, coercion, or a `__post_init__` hook for the new `str` case.
  A `str` must round-trip **as a `str`**, not be coerced to `Path`.
- Anything in `notify/templates.py`, `notify/providers/`, `docs/` or `README.md`.

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `notify/models.py` | MODIFY | One line: widen the `template` annotation on `Message` |

---

## Codebase Contract (Anti-Hallucination)

> **CRITICAL**: This section contains VERIFIED code references from the actual codebase.
> The implementing agent MUST use these exact imports, class names, and method signatures.
> **DO NOT** invent, guess, or assume any import, attribute, or method not listed here.

Verified 2026-08-06 against `dev@f42d302`.

### Verified Imports

```python
# Already present at the top of notify/models.py — NOTHING NEW IS NEEDED
import os                                                    # line 1
import uuid                                                  # line 2
from typing import Any, List, Union, Optional, Literal       # line 3  ← Union already here
from pathlib import Path                                     # line 4  ← Path already here
from datetime import datetime                                # line 5
from dataclasses import InitVar                              # line 6
from email.parser import Parser                              # line 7
from email.policy import default as policy_default           # line 8
from datamodel import BaseModel, Column, Field               # line 9
```

**This task adds no import.** Both `Union` and `Path` are already imported.

### Existing Signatures to Use

```python
# notify/models.py
class Message(BaseModel):                                    # line 80
    name: str = Field(required=True, default=auto_uuid)      # line 89
    body: Union[str, dict] = Field(default=None)             # line 90
    content: str = Field(required=False, default="")         # line 91
    sent: datetime = Field(required=False, default=now)      # line 92
    template: Path                                           # line 93  ← THE ONLY LINE TO CHANGE


class BlockMessage(Message):                                 # line 108 — inherits `template`
    sender: Union[Actor, list[Actor]] = Field(required=False)      # line 117
    recipient: Union[Actor, list[Actor]] = Field(required=False)   # line 118
    content_type: Literal[...] = Field(default_factory=CONTENT_TYPES)  # lines 119-124
    attachments: list[Attachment] = Field(default_factory=list)    # line 125
    flags: list[str]                                               # line 126


class MailMessage(BlockMessage):                             # line 137 — inherits `template`
    directory: str = Field(required=True)                    # line 144
    content: str = Field(required=False)                     # line 145
    attachments: list[MailAttachment]                        # line 146
    raw: InitVar = ""                                        # line 147
    def __post_init__(self, raw: str) -> None: ...           # line 149
```

Note the existing in-file precedent: `body: Union[str, dict]` at line 90 is
already a bare `Union` annotation with a `Field(...)` default, and
`sender: Union[Actor, list[Actor]]` at line 117 is a bare `Union` too. Widening
`template` to a `Union` is idiomatic for this module.

`python-datamodel>=0.3.12` is the modelling library (`pyproject.toml:39`) —
**not** Pydantic. Do not import or reach for `pydantic` here.

### `notify.models.Message` has NO consumers inside `notify/`

Verified via `grep -rn "Message" notify/ --include=*.py`. The package contains
exactly two `Message(` construction sites, and **both import the name from
third-party libraries**, not from `notify.models`:

| File | Line | Import source |
|---|---|---|
| `notify/providers/office365/office365.py` | 13 | `from O365 import (Account, MSOffice365Protocol, Message, Connection, FileSystemTokenBackend)` |
| `notify/providers/gmail/gmail.py` | 10 | `from gmail import GMail as GMailWorker, Message` |

Everything else matching `Message` in the package is either a log string, a
docstring, or an unrelated class (`ThreadMessage`, `BlockMessage` definitions).
This is why the widening is contained: **nothing inside the package constructs
or reads `notify.models.Message.template`.**

### Does NOT Exist

- ~~`notify.models.Message` being used by any provider~~ — see the table above. `office365.py:175`'s `Message(auth=..., protocol=..., con=...)` is the **O365** class, not this one. Do not "update the call site" — there is none to update.
- ~~A `Field(...)` wrapper on `Message.template`~~ — line 93 is a bare annotation today. Keep it bare; adding `Field(required=False)` would change the field's required-ness, which is out of scope.
- ~~`pydantic`~~ — this repo models with `python-datamodel`. `from datamodel import BaseModel, Column, Field` (line 9) is the real import.
- ~~`Message.template_is_source`~~ / ~~`Message.template_source`~~ — not being added. The escape hatch is a `send()` keyword only (TASK-015).
- ~~`tests/test_models.py`~~ — does not exist. The model tests for this task go in `tests/test_jinja_string_templates.py` (TASK-017).

---

## Implementation Notes

### Pattern to Follow

```python
class Message(BaseModel):
    name: str = Field(required=True, default=auto_uuid)
    body: Union[str, dict] = Field(default=None)
    content: str = Field(required=False, default="")
    sent: datetime = Field(required=False, default=now)
    template: Union[Path, str]        # ← was: template: Path
```

That is the entire change.

### Key Constraints

- **`Union[Path, str]`, in that order.** `Path` first preserves the existing
  primary meaning and keeps the diff's intent legible.
- **Do not coerce.** A `str` passed in must come back out as a `str`. If
  `python-datamodel` turns out to coerce `Union` members eagerly, report it in
  the Completion Note rather than working around it with a validator — that
  would be a scope change.
- **Verify `Path` still works.** The regression guard matters more than the new
  capability here: existing callers outside this repo may pass a `Path`.
- Do not reformat, re-sort, or lint-fix unrelated parts of `notify/models.py`.

### Verification command

```bash
git diff --stat notify/models.py
# expected: 1 file changed, 1 insertion(+), 1 deletion(-)
```

If the diff is larger than one line, you have gone out of scope.

### References in Codebase

- `notify/models.py:90` — `body: Union[str, dict]`, the in-file precedent for a bare `Union` annotation.
- `notify/models.py:108`, `:137` — `BlockMessage` / `MailMessage`, which inherit the widened field.

---

## Acceptance Criteria

- [ ] `notify/models.py:93` reads `template: Union[Path, str]`
- [ ] `git diff --stat notify/models.py` shows exactly 1 insertion and 1 deletion
- [ ] `Message(name="x", template=Path("a.html"))` constructs, and `.template` is still a `Path`
- [ ] `Message(name="x", template="{{ who }}")` constructs, and `.template == "{{ who }}"` as a `str` (not coerced to `Path`)
- [ ] `BlockMessage(name="x", template="{{ who }}")` constructs — the widening is inherited
- [ ] No new import added to `notify/models.py`
- [ ] `from notify.models import Message, BlockMessage, MailMessage` still works
- [ ] No linting errors: `.venv/bin/python -m ruff check notify/models.py`
- [ ] Existing suite still green: `.venv/bin/python -m pytest tests/ -v`

---

## Test Specification

> Formal tests land in TASK-017. Use this scaffold to self-verify before handing off.

```python
from pathlib import Path
from notify.models import Message, BlockMessage


class TestMessageTemplateWidening:
    def test_accepts_path(self):
        """Regression guard — the original meaning must survive."""
        m = Message(name="x", template=Path("a.html"))
        assert isinstance(m.template, Path)

    def test_accepts_str(self):
        m = Message(name="x", template="{{ who }}")
        assert m.template == "{{ who }}"
        assert isinstance(m.template, str)

    def test_blockmessage_inherits_widening(self):
        b = BlockMessage(name="x", template="{{ who }}")
        assert b.template == "{{ who }}"
```

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** at `sdd/specs/jinja-string-notify.spec.md` — §1 G8, §3 Module 3, §9 Q5.
2. **Check dependencies** — none. This task can run before, after, or alongside
   TASK-014/015; it shares no file with them.
3. **Verify the Codebase Contract** before writing ANY code:
   - Confirm `notify/models.py:93` still reads `template: Path`.
   - Confirm `Union` (line 3) and `Path` (line 4) are still imported.
   - **NEVER** reference an import, attribute, or method not in the contract
     without verifying it exists.
4. **Update status** in `sdd/tasks/index/jinja-string-notify.json` → `"in-progress"`.
5. **Implement** — one line. Resist every temptation to improve neighbouring code.
6. **Verify** every acceptance criterion, especially the one-line diff.
7. **Move this file** to `sdd/tasks/completed/TASK-016-widen-message-template.md`.
8. **Update index** → `"done"`.
9. **Fill in the Completion Note** below.

---

## Completion Note

*(Agent fills this in when done)*

**Completed by**: <session or agent ID>
**Date**: YYYY-MM-DD
**Notes**: What was implemented, any deviations from scope, issues encountered.

**Deviations from spec**: none | describe if any
