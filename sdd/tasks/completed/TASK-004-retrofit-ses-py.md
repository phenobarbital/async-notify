# TASK-004: Retrofit `notify/providers/ses/ses.py` to delegate MIME to `_mime_utils`

**Feature**: FEAT-001 — UTF-8 handling in email providers (NAV-8390)
**Spec**: `sdd/specs/NAV-8390-email-utf8.spec.md`
**Status**: pending
**Priority**: medium
**Estimated effort**: S (< 2h)
**Depends-on**: TASK-001
**Assigned-to**: unassigned

---

## Context

`notify/providers/ses/ses.py` extends `ProviderEmail` but overrides
`_render_` (line 79) and builds its own `MIMEMultipart` with the same UTF-8
bugs. Because it shadows the base's `_render_`, fixing `ProviderEmail`
(TASK-002) does NOT fix `Ses`. This task is required to bring SES into the
helper.

`Ses._send_` (line 103) uses the AWS SES API (`send_raw_email` /
`send_templated_email`) and is unchanged by this task — only the
MIME-building `_render_` is retrofitted.

Implements Spec §3 Module 4. Resolves brainstorm Q2 (SES in scope).

---

## Scope

- Rewrite `Ses._render_` (lines 79–101) to use `_mime_utils`:
  - Build the envelope with `build_alternative_message(sender=self.sender_email,
    to=to.account.address, subject=subject)`.
  - Attach plain part via `attach_text_part(msg, content, "plain")`.
  - Attach HTML part via `attach_text_part(msg, content, "html")`.
- Preserve template rendering via `await self._template.render_async(...)`.
  `Ses._render_` is `async`.
- Preserve return type: return the assembled `MIMEMultipart` exactly as
  before (`_send_` at line 128 awaits it and passes it to SES).
- Imports: add `from notify.providers import _mime_utils as _mu`. Remove
  unused `from email.mime.multipart import MIMEMultipart` and
  `from email.mime.text import MIMEText` after delegation.

**NOT in scope**:
- Touching `mail.py` or `smtp.py` (TASK-002, TASK-003).
- Touching `connect`, `close`, `_send_` (SES API path) — unchanged.
- The SES template path (`use_aws_template=True` at line 112) — uses AWS
  templates, not MIME. Unchanged.
- Writing tests (TASK-006).

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `notify/providers/ses/ses.py` | MODIFY | Replace `_render_`; prune unused imports. |

---

## Codebase Contract (Anti-Hallucination)

### Verified Imports

```python
# Existing imports in ses.py (lines 1–16) — keep what's still used:
from typing import Optional, Union, Any               # KEEP — signatures
from collections.abc import Callable                  # KEEP
import asyncio                                        # check usage
from email.mime.multipart import MIMEMultipart        # DROP after retrofit
from email.mime.text import MIMEText                  # DROP after retrofit
from aiobotocore.session import get_session           # KEEP — connect()
from botocore.exceptions import ClientError           # KEEP — _send_
from navconfig.logging import logging                 # KEEP
from notify.providers.mail import ProviderEmail       # KEEP — base class
from notify.models import Actor                       # KEEP — typing
from notify.conf import (                             # KEEP — config
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION_NAME, AWS_SENDER_EMAIL,
)

# New import to add:
from notify.providers import _mime_utils as _mu       # provided by TASK-001
```

### Existing Signatures to Use

```python
# notify/providers/ses/ses.py
class Ses(ProviderEmail):                                              # line 22
    provider = "amazon_ses"                                            # line 25
    blocking: str = "asyncio"                                          # line 26

    def __init__(self, *args, aws_access_key_id=None, aws_secret_access_key=None,
                 aws_region_name=None, sender_email=None, use_aws_template=False,
                 template_name=None, **kwargs): ...                    # line 28
    async def connect(self, **kwargs): ...                             # line 68
    async def close(self): ...                                         # line 73

    # === REWRITE ===
    async def _render_(self, to, message=None, subject=None, **kwargs): # line 79  REWRITE body
        # current body (lines 80–101):
        #   if self._template: content = await self._template.render_async(...)
        #   else: content = kwargs.get("body") or message
        #   email_msg = MIMEMultipart("alternative")                   # line 95
        #   email_msg["Subject"] = subject                             # line 96  ← raw assign
        #   email_msg["From"] = self.sender_email                      # line 97  ← raw assign
        #   email_msg["To"] = to.account.address                       # line 98  ← raw assign
        #   email_msg.attach(MIMEText(content, "plain"))               # line 99  ← no _charset
        #   email_msg.attach(MIMEText(content, "html"))                # line 100 ← no _charset
        #   return email_msg

    # === KEEP unchanged ===
    async def _send_(self, to, message, subject, client=None, **kwargs): ...  # line 103
```

```python
# notify/providers/_mime_utils.py — TASK-001 deliverable
def build_alternative_message(*, sender, to, subject, reply_to=None) -> MIMEMultipart: ...
def attach_text_part(msg, body, subtype='plain') -> None: ...
def format_address(actor) -> str: ...
```

### Does NOT Exist
- ~~`Ses._send_` builds MIME itself~~ — `_send_` either takes the rendered
  `MIMEMultipart` from `_render_` (the path we fix) or uses AWS SES
  template ID (no MIME, unchanged).
- ~~`Ses` calls `super()._render_()`~~ — it does NOT. The override at
  line 79 is total; fixing the base does not fix Ses.
- ~~`Ses.actor`~~ — Ses uses `self.sender_email`, NOT `self.actor`. Do not
  substitute one for the other.
- ~~Multiple-recipient `To` handling~~ — Ses today accepts a single
  `Actor` and uses `to.account.address`. Do not change this contract; the
  helper accepts `str | list[str]` and works either way.

---

## Implementation Notes

### Pattern to Follow

```python
# notify/providers/ses/ses.py — new _render_ body (replaces lines 79–101)
async def _render_(
    self,
    to: Actor,
    message: str = None,
    subject: str = None,
    **kwargs,
) -> 'MIMEMultipart':
    """Create a UTF-8-safe email message for AWS SES."""
    if self._template:
        templateargs = {
            "recipient": to,
            "username": to,
            "message": message,
            "content": message,
            **kwargs,
        }
        content = await self._template.render_async(**templateargs)
    else:
        try:
            content = kwargs["body"]
        except KeyError:
            content = message

    msg = _mu.build_alternative_message(
        sender=self.sender_email,
        to=to.account.address,
        subject=subject,
    )
    _mu.attach_text_part(msg, content, "plain")
    _mu.attach_text_part(msg, content, "html")
    return msg
```

### Key Constraints

- Must remain `async def _render_` — `_send_` awaits it at line 128.
- Use `self.sender_email` (set in `__init__` at line 49), NOT `self.actor`.
- `_send_` (line 103) is **untouched**. Reading it during your work is fine;
  modifying it is out of scope.
- After retrofit, `grep -n "MIMEMultipart\|MIMEText" notify/providers/ses/ses.py`
  should return zero matches. Prune the now-unused imports.

### References in Codebase

- `notify/providers/ses/ses.py:79-101` — current `_render_` body to rewrite.
- `notify/providers/ses/ses.py:128` — call site `_send_` uses the result;
  read for context but don't edit.

---

## Acceptance Criteria

- [ ] `_render_` body no longer contains literal `MIMEMultipart` or
      `MIMEText` calls.
- [ ] `email.mime.*` imports removed (`ruff check notify/providers/ses/ses.py`
      clean under `F401`).
- [ ] `_render_` is still `async def`: `python -c "import inspect; from
      notify.providers.ses.ses import Ses; print(inspect.iscoroutinefunction(Ses._render_))"`
      → `True`.
- [ ] `python -c "from notify.providers.ses.ses import Ses; print(Ses)"`
      succeeds (no import-time errors).
- [ ] `_send_` (line 103) is byte-identical to pre-retrofit:
      `git diff notify/providers/ses/ses.py` shows changes only between
      lines 79–101 and the import block.

---

## Test Specification

Tests live in `tests/test_email_utf8.py` (TASK-006).

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** at `sdd/specs/NAV-8390-email-utf8.spec.md` — §3 Module 4,
   §6 Codebase Contract, §7 Risk #7 (`client` kwarg on `_send_`).
2. **Verify TASK-001 is complete** — helper module must exist.
3. **Verify the Codebase Contract** — confirm `Ses._render_` is at line 79
   (line numbers may have shifted; re-read before editing).
4. **Implement** per the pattern above.
5. **Verify** all acceptance criteria locally.
6. **Move this file** to `sdd/tasks/completed/TASK-004-retrofit-ses-py.md`.
7. **Update index** → `"done"`.
8. **Fill in the Completion Note** below.

---

## Completion Note

**Completed by**: claude-sonnet-4-6 (SDD Worker)
**Date**: 2026-05-13
**Notes**: Rewrote _render_ to use _mime_utils. Removed MIMEMultipart and
MIMEText imports. asyncio kept (used in send()). Union/Any/Optional kept (used
in send() and __init__ signatures). _send_ path unchanged.
**Deviations from spec**: none
