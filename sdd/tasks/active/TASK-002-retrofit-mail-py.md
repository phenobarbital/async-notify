# TASK-002: Retrofit `notify/providers/mail.py` to delegate MIME to `_mime_utils`

**Feature**: FEAT-001 — UTF-8 handling in email providers (NAV-8390)
**Spec**: `sdd/specs/NAV-8390-email-utf8.spec.md`
**Status**: pending
**Priority**: medium
**Estimated effort**: S (< 2h)
**Depends-on**: TASK-001
**Assigned-to**: unassigned

---

## Context

`ProviderEmail._render_` and `ProviderEmail.add_attachment` in
`notify/providers/mail.py` build MIME messages without UTF-8 awareness.
This task replaces those implementations with thin pass-throughs to the
`_mime_utils` helper created in TASK-001.

Also deletes `_prepare_message` (lines 112–131), which is defined but
never called from `send()` (`send()` calls `_prepare_` on `ProviderBase`,
not `_prepare_message`). Resolved Q1 in spec §8.

Implements Spec §3 Module 2.

`Email` and `Aws` are thin subclasses that inherit `_render_` unchanged
— fixing the base fixes them automatically (verified: `aws/aws.py:17-68`
has no `_render_` definition; `email/email.py:11-…` likewise).

---

## Scope

- Rewrite `ProviderEmail._render_` (lines 133–168) so it calls
  `_mime_utils.build_alternative_message(...)` for the envelope and
  `_mime_utils.attach_text_part(...)` for both the plain and HTML parts.
- Rewrite `ProviderEmail.add_attachment` (lines 170–182) so it calls
  `_mime_utils.attach_file(...)`.
- Preserve the existing public signatures verbatim: `_render_(self, to=None,
  message=None, subject=None, **kwargs)` and `add_attachment(self, message,
  filename, mimetype="octect-stream")` — note `mimetype` kwarg name and
  spelling preserved for backwards compatibility; pass-through ignores the
  misspelled default when `mimetype` doesn't actually match the IANA form.
- Preserve template rendering: text part attached first, HTML attached second.
- Preserve `msg["sender"] = self.actor` (mail.py:151 has it; smtp.py has it
  commented out — that asymmetry is retained per spec §7 Risk #1).
- **Delete** the `_prepare_message` method (mail.py:112–131). Verified
  unreferenced via `grep -rn "_prepare_message" notify/` (returns only the
  two definitions, no callers).
- Imports: add `from notify.providers import _mime_utils as _mu` (or
  similar). Remove now-unused imports from `email.mime.*` and
  `email.utils` once delegation is complete.

**NOT in scope**:
- Touching `smtp.py` or `ses.py` (TASK-003, TASK-004).
- Touching `connect`, `close`, `is_connected`, `send`, `_send_` — these
  stay byte-for-byte identical.
- Changing the `actor` attribute parsing strategy beyond what
  `_mime_utils.format_address` already does.
- Bumping `aiosmtplib` (TASK-005).
- Writing tests (TASK-006).

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `notify/providers/mail.py` | MODIFY | Replace `_render_`, `add_attachment`; delete `_prepare_message`; prune unused imports. |

---

## Codebase Contract (Anti-Hallucination)

### Verified Imports

```python
# Existing imports in mail.py (lines 1–20) — keep what's still used, drop the rest:
import os                                             # still used? — likely droppable after retrofit
import ssl                                            # KEEP — used in connect()
import asyncio                                        # KEEP — used in send()
from abc import ABC                                   # KEEP — class is ABC
from typing import Union, Any                         # KEEP — used in signatures
from collections.abc import Callable                  # KEEP — typing
from email import encoders                            # DROP — was only in add_attachment
from email.mime.multipart import MIMEMultipart        # DROP — was only in _render_
from email.mime.base import MIMEBase                  # DROP — was only in add_attachment
from email.mime.text import MIMEText                  # DROP — was only in _render_
from email.mime.image import MIMEImage                # DROP — was only in add_attachment
from email.utils import formatdate                    # DROP — moved into helper
from functools import partial                         # check usage; likely droppable
import aiosmtplib                                     # KEEP — connect/send use it
from notify.models import Actor                       # KEEP — typing
from notify.exceptions import ProviderError           # KEEP — used in send()
from .base import ProviderBase, ProviderType          # KEEP — class inheritance

# New import to add:
from notify.providers import _mime_utils as _mu       # provided by TASK-001
```

### Existing Signatures to Use

```python
# notify/providers/mail.py
class ProviderEmail(ProviderBase, ABC):                                # line 23
    provider_type = ProviderType.EMAIL                                 # line 30
    blocking: str = 'asyncio'                                          # line 31
    timeout: int = 60                                                  # line 32

    def __init__(self, *args, **kwargs): ...                           # line 34  KEEP unchanged
    async def close(self): ...                                         # line 44  KEEP unchanged
    async def connect(self, *args, **kwargs): ...                      # line 55  KEEP unchanged
    def is_connected(self): ...                                        # line 106 KEEP unchanged

    # === DELETE ===
    def _prepare_message(self, to_address, message, content): ...      # line 112  DEAD — DELETE entire method

    # === REWRITE ===
    async def _render_(self, to=None, message=None, subject=None, **kw): # line 133  REWRITE body
    def add_attachment(self, message, filename, mimetype="octect-stream"): ... # line 170  REWRITE body

    # === KEEP unchanged ===
    async def _send_(self, to, message, subject, **kwargs):            # line 184
    async def send(self, recipient=None, message=None, subject=None, **kwargs): ...  # line 212
```

```python
# notify/providers/_mime_utils.py  (from TASK-001 — re-verify it landed)
def parse_actor(actor: str) -> tuple[str, str]: ...
def format_address(actor: str) -> str: ...
def build_alternative_message(*, sender: str, to: str | list[str],
                              subject: str | None,
                              reply_to: str | None = None) -> MIMEMultipart: ...
def attach_text_part(msg: MIMEMultipart, body: str, subtype: str = "plain") -> None: ...
def attach_file(msg: MIMEMultipart, path: str | os.PathLike,
                mimetype: str | None = None) -> None: ...
```

### Does NOT Exist
- ~~`ProviderEmail.add_attachment` with `path` kwarg~~ — the parameter is
  `filename` (and `message` is the first positional arg). Preserve.
- ~~`ProviderEmail._prepare_message` is called from `send()`~~ — verified
  unreferenced. `send()` at mail.py:235 calls `self._prepare_(...)` on
  `ProviderBase`, not `_prepare_message`.
- ~~`MIMEImage` is needed after retrofit~~ — `_mime_utils.attach_file`
  handles image attachments via the same `MIMEBase` + base64 path; we no
  longer need a special-case for `image/png`. (Behavior change: today's
  `add_attachment` builds a `MIMEImage` for `image/png`; after retrofit,
  it builds a `MIMEBase('image', 'png')` with base64 encoding. End-result
  bytes are equivalent for SMTP transport.)

---

## Implementation Notes

### Pattern to Follow

```python
# notify/providers/mail.py — new _render_ body (replaces lines 133–168)
async def _render_(
    self,
    to: Actor = None,
    message: str = None,
    subject: str = None,
    **kwargs,
) -> 'MIMEMultipart':
    """Build a UTF-8-safe multipart/alternative message."""
    recipient = (
        to.account.address if not isinstance(to, list)
        else ", ".join(to)
    )
    msg = _mu.build_alternative_message(
        sender=self.actor,
        to=recipient,
        subject=subject,
    )
    # Preserve mail.py's historical 'sender' header assignment (smtp.py omits this — see spec §7 Risk #1)
    msg["sender"] = _mu.format_address(self.actor)
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
        content = await self._template.render_async(**self._templateargs)
    else:
        content = message
    _mu.attach_text_part(msg, content, "html")
    return msg


# notify/providers/mail.py — new add_attachment body (replaces lines 170–182)
def add_attachment(
    self,
    message: 'MIMEMultipart',
    filename: str,
    mimetype: str = "octect-stream",
) -> None:
    """Attach a file to `message` with RFC 2231 filename encoding.

    `mimetype` kwarg accepted for backwards-compatibility. The misspelled
    default ("octect-stream") is treated as 'unknown' and resolved via
    mimetypes.guess_type; callers can still pass an explicit, properly
    spelled type to override.
    """
    resolved = None if mimetype in ("octect-stream", "application/octet-stream") else mimetype
    _mu.attach_file(message, filename, resolved)
```

### Key Constraints

- The `_render_` rewrite must remain `async def` — template rendering uses
  `render_async`. Even though `_mime_utils` is sync, the awaiting still
  happens at the `_render_` level.
- Do **not** change the `mimetype="octect-stream"` parameter default —
  external callers may have been passing the misspelled value. The
  internal logic just treats it as "unknown" and defers to mimetypes.
- The line `msg["sender"] = self.actor` (today at mail.py:151) is rewritten
  to use `format_address` so non-ASCII sender display names are also
  RFC-2047 encoded. This is intentional per spec §1 Goals.
- Preserve `msg.preamble = subject` if it exists today; this is the
  fallback display string for clients that can't parse multipart.
- After retrofit, run `grep -n "MIMEText\|MIMEMultipart\|MIMEBase\|MIMEImage\|formatdate"
  notify/providers/mail.py` and confirm zero matches. Prune unused
  imports accordingly.

### References in Codebase

- `notify/providers/mail.py:133-168` — current `_render_` to rewrite.
- `notify/providers/mail.py:170-182` — current `add_attachment` to rewrite.
- `notify/providers/mail.py:112-131` — dead `_prepare_message` to delete.
- `notify/providers/email/email.py` and `notify/providers/aws/aws.py` —
  inheriting subclasses; read briefly to confirm they don't override
  `_render_` or `add_attachment`.

---

## Acceptance Criteria

- [ ] `_prepare_message` is gone from `mail.py`: `grep -n
      "_prepare_message" notify/providers/mail.py` → only zero matches.
- [ ] `_render_` body no longer contains literal `MIMEMultipart` or
      `MIMEText` calls: `grep -n "MIMEMultipart\|MIMEText" notify/providers/mail.py`
      → zero matches.
- [ ] `add_attachment` no longer constructs `MIMEImage` / `MIMEBase`
      directly: `grep -n "MIMEImage\|MIMEBase" notify/providers/mail.py`
      → zero matches.
- [ ] Unused imports pruned (`ruff check notify/providers/mail.py` clean
      under `F401`).
- [ ] `python -c "from notify.providers.mail import ProviderEmail;
      print(ProviderEmail)"` succeeds.
- [ ] `python -c "from notify.providers.email.email import Email;
      print(Email)"` succeeds (inheriting subclass still imports).
- [ ] `python -c "from notify.providers.aws.aws import Aws; print(Aws)"`
      succeeds.
- [ ] All preserved-method signatures unchanged (verify with `inspect`).

---

## Test Specification

Tests live in `tests/test_email_utf8.py` (TASK-006). Smoke check the
agent may run before marking the task done:

```python
import asyncio
from notify.providers.mail import ProviderEmail
print(hasattr(ProviderEmail, "_prepare_message"))  # expect: False
print(asyncio.iscoroutinefunction(ProviderEmail._render_))  # expect: True
```

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** at `sdd/specs/NAV-8390-email-utf8.spec.md` — §3 Module 2,
   §6 Codebase Contract, §7 Risk #1 (sender asymmetry) and Risk #2 (`octect`
   typo).
2. **Verify TASK-001 is complete** — `ls sdd/tasks/completed/ | grep TASK-001`
   should match; `notify/providers/_mime_utils.py` must exist and import.
3. **Verify the Codebase Contract** — re-run the greps before editing.
4. **Implement** per the pattern above.
5. **Verify** all acceptance criteria locally.
6. **Move this file** to `sdd/tasks/completed/TASK-002-retrofit-mail-py.md`.
7. **Update index** `sdd/tasks/index/NAV-8390-email-utf8.json` → `"done"`.
8. **Fill in the Completion Note** below.

---

## Completion Note

*(Agent fills this in when done)*

**Completed by**:
**Date**:
**Notes**:
**Deviations from spec**: none | describe if any
