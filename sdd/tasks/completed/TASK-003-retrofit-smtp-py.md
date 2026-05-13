# TASK-003: Retrofit `notify/providers/smtp/smtp.py` to delegate MIME to `_mime_utils`

**Feature**: FEAT-001 — UTF-8 handling in email providers (NAV-8390)
**Spec**: `sdd/specs/NAV-8390-email-utf8.spec.md`
**Status**: pending
**Priority**: medium
**Estimated effort**: S (< 2h)
**Depends-on**: TASK-001
**Assigned-to**: unassigned

---

## Context

`notify/providers/smtp/smtp.py` is the synchronous-stdlib-`smtplib` variant of
the email provider, structurally duplicating most of `ProviderEmail` but
inheriting from `ProviderBase` directly (not from `ProviderEmail`). It has the
same UTF-8 bug shape on `_render_` and `add_attachment`.

This task is the sync sibling of TASK-002. Also deletes the dead
`_prepare_message` (line 154) — verified unreferenced via
`grep -rn "_prepare_message" notify/` which returned only the two
definitions (mail.py:112 and smtp.py:154), no callers.

Implements Spec §3 Module 3. Resolves the first new open question in spec §8
(symmetric `_prepare_message` deletion).

---

## Scope

- Rewrite `SMTP._render_` (lines 175–210) to delegate to `_mime_utils`.
  Note: this method is `def`, NOT `async def`. The template rendering uses
  `self._template.render(...)` (sync), not `render_async`.
- Rewrite `SMTP.add_attachment` (~line 212) to call `_mime_utils.attach_file`.
- **Delete** `SMTP._prepare_message` (line 154) — symmetric with TASK-002.
- Preserve the existing public signatures: `_render_(self, to, message=None,
  subject=None, **kwargs)` and `add_attachment(self, message, filename,
  mimetype="octect-stream")`.
- Preserve template rendering order: text first, HTML second.
- Do **not** set `msg["sender"]` — smtp.py has this assignment commented out
  today (line ~193). Asymmetry with mail.py is intentional per spec §7 Risk #1.
- Add `from notify.providers import _mime_utils as _mu`. Prune unused
  imports from `email.mime.*`, `email.utils`, and `email` after delegation.

**NOT in scope**:
- Touching `mail.py` or `ses.py` (TASK-002, TASK-004).
- Touching `connect`, `close`, `_send_`, `send` — these stay unchanged.
- Migrating from `smtplib` to `aiosmtplib`. The sync path is intentional.
- Writing tests (TASK-006).

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `notify/providers/smtp/smtp.py` | MODIFY | Replace `_render_`, `add_attachment`; delete `_prepare_message`; prune unused imports. |

---

## Codebase Contract (Anti-Hallucination)

### Verified Imports

```python
# Existing imports in smtp.py (lines 1–25) — keep what's still used:
import os                                             # check usage
import ssl                                            # KEEP if used in connect()
import asyncio                                        # check usage
from typing import Union, Any                         # KEEP — signatures
from collections.abc import Callable                  # KEEP — typing
from email import encoders                            # DROP — moved into helper
from email.mime.multipart import MIMEMultipart        # DROP
from email.mime.base import MIMEBase                  # DROP
from email.mime.text import MIMEText                  # DROP
from email.mime.image import MIMEImage                # DROP
from email.utils import formatdate                    # DROP
import smtplib                                        # KEEP — connect/send use it
from notify.models import Actor                       # KEEP — typing
from notify.exceptions import ProviderError           # KEEP
from notify.providers.base import ProviderBase, ProviderType  # KEEP — class inheritance
from notify.providers.message import ThreadMessage    # check usage
from notify.conf import (                             # KEEP — config
    EMAIL_SMTP_USERNAME, EMAIL_SMTP_PASSWORD, EMAIL_SMTP_HOST, EMAIL_SMTP_PORT,
)

# New import to add:
from notify.providers import _mime_utils as _mu       # provided by TASK-001
```

### Existing Signatures to Use

```python
# notify/providers/smtp/smtp.py
class SMTP(ProviderBase):                                              # line 28  (class name is "SMTP" — caps)
    provider_type = ProviderType.EMAIL                                 # line 35
    blocking: str = 'executor'                                         # line 36  (differs from ProviderEmail.blocking='asyncio')
    timeout: int = 60                                                  # line 37

    def __init__(self, hostname=None, port=None, username=None, password=None, **kwargs): ...  # line 39

    # === DELETE ===
    def _prepare_message(self, to_address, message, content): ...      # line 154  DEAD — DELETE entire method

    # === REWRITE ===
    def _render_(self, to, message=None, subject=None, **kwargs):      # line 175  REWRITE body (SYNC, not async)
    def add_attachment(self, message, filename, mimetype="octect-stream"): ...  # line ~212  REWRITE body

    # === KEEP unchanged ===
    def _send_(self, to, message, subject, **kwargs):                  # line 226
```

```python
# notify/providers/_mime_utils.py — TASK-001 deliverable
def build_alternative_message(*, sender, to, subject, reply_to=None) -> MIMEMultipart: ...
def attach_text_part(msg, body, subtype='plain') -> None: ...
def attach_file(msg, path, mimetype=None) -> None: ...
def format_address(actor) -> str: ...
```

### Does NOT Exist
- ~~`notify.providers.smtp.Smtp`~~ — class is `SMTP` (all caps).
- ~~`SMTP._render_` is async~~ — it's SYNC `def _render_`. Do not wrap
  the helper calls in `await`.
- ~~`SMTP` extends `ProviderEmail`~~ — it extends `ProviderBase` directly.
  Confirms why `_prepare_message` is dead here too: there's no shared
  caller upstream.
- ~~`SMTP.actor`~~ — verify before referencing. If `actor` is set
  elsewhere on the instance, fine; if not, fall back to the `username`
  attribute. The implementing agent must verify with `grep -n
  "self.actor\|self.username" notify/providers/smtp/smtp.py`.

---

## Implementation Notes

### Pattern to Follow

```python
# notify/providers/smtp/smtp.py — new _render_ body (replaces lines 175–210)
def _render_(
    self,
    to: Actor,
    message: str = None,
    subject: str = None,
    **kwargs,
) -> 'MIMEMultipart':
    """Build a UTF-8-safe multipart/alternative message (sync variant)."""
    sender = getattr(self, "actor", None) or self.username
    recipient = (
        to.account.address if not isinstance(to, list)
        else ", ".join(to)
    )
    msg = _mu.build_alternative_message(
        sender=sender,
        to=recipient,
        subject=subject,
    )
    # NOTE: smtp.py historically did NOT set msg["sender"] (it was commented
    # out at line ~193). Intentional asymmetry with mail.py — preserved.
    msg.preamble = subject or ""

    if message:
        _mu.attach_text_part(msg, message, "plain")

    if self._template:
        self._templateargs = {
            "recipient": to,
            "username": to,
            "message": message,
            "content": message,
            **kwargs,
        }
        content = self._template.render(**self._templateargs)
    else:
        content = message
    _mu.attach_text_part(msg, content, "html")
    return msg


# notify/providers/smtp/smtp.py — new add_attachment body
def add_attachment(
    self,
    message: 'MIMEMultipart',
    filename: str,
    mimetype: str = "octect-stream",
) -> None:
    """Attach a file with RFC 2231 filename encoding."""
    resolved = None if mimetype in ("octect-stream", "application/octet-stream") else mimetype
    _mu.attach_file(message, filename, resolved)
```

### Key Constraints

- `_render_` MUST remain synchronous (`def`, not `async def`). This is the
  sole structural difference from TASK-002's mail.py retrofit.
- Use `self._template.render(...)` (sync), NOT `render_async`.
- Do NOT set `msg["sender"]` — preserves the today-behavior asymmetry per
  spec §7 Risk #1.
- After retrofit, run `grep -n "MIMEText\|MIMEMultipart\|MIMEBase\|MIMEImage\|formatdate"
  notify/providers/smtp/smtp.py` and confirm zero matches. Prune unused
  imports.

### References in Codebase

- `notify/providers/smtp/smtp.py:175-210` — current `_render_` to rewrite.
- `notify/providers/smtp/smtp.py:~212-…` — current `add_attachment` to rewrite.
- `notify/providers/smtp/smtp.py:154-…` — dead `_prepare_message` to delete.

---

## Acceptance Criteria

- [ ] `_prepare_message` is gone from `smtp.py`: `grep -n "_prepare_message"
      notify/providers/smtp/smtp.py` → zero matches.
- [ ] `_render_` body no longer contains literal `MIMEMultipart` or
      `MIMEText` calls.
- [ ] `add_attachment` no longer constructs `MIMEImage` / `MIMEBase`
      directly.
- [ ] Unused imports pruned (`ruff check notify/providers/smtp/smtp.py`
      clean under `F401`).
- [ ] `python -c "from notify.providers.smtp.smtp import SMTP; print(SMTP)"`
      succeeds.
- [ ] `_render_` remains synchronous: `python -c "import inspect; from
      notify.providers.smtp.smtp import SMTP; print(inspect.iscoroutinefunction(SMTP._render_))"`
      → `False`.

---

## Test Specification

Tests live in `tests/test_email_utf8.py` (TASK-006). No new test file in
this task.

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** at `sdd/specs/NAV-8390-email-utf8.spec.md` — §3 Module 3,
   §6 Codebase Contract, §7 Risk #1 (no `msg["sender"]` on smtp.py).
2. **Verify TASK-001 is complete** — helper module must exist.
3. **Verify the Codebase Contract** — re-grep `_prepare_message` to confirm
   it's still unreferenced before deleting.
4. **Implement** per the pattern above. Watch the sync vs async difference
   vs. TASK-002.
5. **Verify** all acceptance criteria locally.
6. **Move this file** to `sdd/tasks/completed/TASK-003-retrofit-smtp-py.md`.
7. **Update index** → `"done"`.
8. **Fill in the Completion Note** below.

---

## Completion Note

**Completed by**: claude-sonnet-4-6 (SDD Worker)
**Date**: 2026-05-13
**Notes**: Deleted _prepare_message, rewrote _render_ (sync) and add_attachment
to delegate to _mime_utils. Pruned all unused imports (os, asyncio, Union, Any,
ThreadMessage, email.mime.*, email.utils, encoders). Preserved no-sender-header
asymmetry per spec §7 Risk #1.
**Deviations from spec**: none
