# TASK-001: Create `_mime_utils.py` helper module

**Feature**: FEAT-001 — UTF-8 handling in email providers (NAV-8390)
**Spec**: `sdd/specs/NAV-8390-email-utf8.spec.md`
**Status**: pending
**Priority**: high
**Estimated effort**: S (< 2h)
**Depends-on**: none
**Assigned-to**: unassigned

---

## Context

Foundation task for FEAT-001. Three providers (`mail.py`, `smtp/smtp.py`,
`ses/ses.py`) duplicate broken MIME construction code that mangles non-ASCII
subjects, body parts, address display names, and attachment filenames.

This task creates a single private helper module — `notify/providers/_mime_utils.py`
— that the retrofits in TASK-002, TASK-003, and TASK-004 will delegate to.

Implements Spec §2 (Architectural Design → Helper API) and §3 (Module 1).

---

## Scope

- Create `notify/providers/_mime_utils.py` exposing five functions:
  `parse_actor`, `format_address`, `build_alternative_message`,
  `attach_text_part`, `attach_file`.
- Module must be **stdlib-only** (no `notify.*` imports — keep it leaf-level
  to avoid import cycles).
- Module is **synchronous** — no `async def`. Callers handle template
  rendering's `await` themselves.
- Do **not** export from `notify/providers/__init__.py`. The leading
  underscore signals private.

**NOT in scope**:
- Retrofitting `mail.py`, `smtp.py`, or `ses.py` (TASK-002, 003, 004).
- Writing tests for the helper (TASK-006 contains all tests for this feature).
- Bumping `aiosmtplib` (TASK-005).
- Inline-image / `Content-ID` support, S/MIME, DKIM (spec §1 Non-Goals).

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `notify/providers/_mime_utils.py` | CREATE | The helper module — 5 functions, stdlib-only. |

---

## Codebase Contract (Anti-Hallucination)

### Verified Imports
```python
# Stdlib only — all available on Python 3.9+:
import os
import mimetypes
from email import policy as email_policy
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, parseaddr
from email import encoders
```

### Existing Signatures to Use
```python
# Stdlib references (Python 3.9):

# email.policy.SMTPUTF8 — module-level Policy instance.
# Pass directly to MIMEMultipart(..., policy=email_policy.SMTPUTF8).

# email.header.Header(s: str | None, charset: str = 'utf-8') -> Header
# Returns an object that, when assigned to a header field, serializes as
# RFC 2047 encoded-word when needed.

# email.utils.formataddr((display_name, addr), charset='utf-8') -> str
# Returns 'Display <addr>' with RFC-2047 quoting of display_name when needed.

# email.utils.parseaddr(addr) -> tuple[str, str]
# Returns (display_name, addr); display_name is '' if absent.

# email.mime.text.MIMEText(text: str, subtype: str = 'plain', _charset: str | None = None)
# When _charset='utf-8', Content-Type gets charset="utf-8" and the body is
# QP/base64 encoded as needed.

# email.mime.multipart.MIMEMultipart(_subtype: str = 'mixed', boundary=None,
#                                    _subparts=None, *, policy=compat32, **_params)

# email.mime.base.MIMEBase(_maintype, _subtype, *, policy=compat32, **_params)

# mimetypes.guess_type(url: str, strict: bool = True) -> tuple[str | None, str | None]
# Returns (type, encoding); type looks like 'application/pdf'. Split on '/'
# for maintype/subtype. Falls back to (None, None) for unknown extensions —
# helper must default to 'application/octet-stream' in that case.
```

### Does NOT Exist
- ~~`notify.providers._mime_utils`~~ — does not exist yet; this task creates it.
- ~~`email.policy.smtputf8`~~ — lowercase. The constant is **`SMTPUTF8`** (caps).
- ~~`email.utils.formataddr(addr, charset='utf-8')`~~ — first arg must be a
  **2-tuple** `(name, addr)`, not a string. Use `parseaddr` first if you
  only have a string.
- ~~`MIMEText` with `charset=` kwarg~~ — the parameter is `_charset` (leading
  underscore), positional or keyword.

---

## Implementation Notes

### Pattern to Follow

```python
# notify/providers/_mime_utils.py
"""Private MIME-construction helpers shared by mail/smtp/ses providers.

This module is intentionally:
  - stdlib-only (no `notify.*` imports)
  - synchronous (callers await template rendering themselves)
  - private (leading underscore; not exported from __init__.py)
"""
import os
import mimetypes
from pathlib import Path
from typing import Optional, Union
from email import encoders
from email import policy as email_policy
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, parseaddr


def parse_actor(actor: str) -> tuple[str, str]:
    """Split an actor string into (display_name, address).

    Accepts either 'Name <addr@host>' or 'addr@host'.
    Returns ('', addr) when no display name is present.
    """
    name, addr = parseaddr(actor or "")
    return name, addr


def format_address(actor: str) -> str:
    """Return an RFC-2047-encoded header value for From/To/Sender.

    Wraps email.utils.formataddr((name, addr), charset='utf-8'). Returns
    the raw string unchanged when actor is empty.
    """
    if not actor:
        return ""
    name, addr = parse_actor(actor)
    return formataddr((name, addr), charset='utf-8')


def build_alternative_message(
    *,
    sender: str,
    to: Union[str, list[str]],
    subject: Optional[str],
    reply_to: Optional[str] = None,
) -> MIMEMultipart:
    """Construct a 'multipart/alternative' envelope with UTF-8 policy."""
    msg = MIMEMultipart("alternative", policy=email_policy.SMTPUTF8)
    msg["From"] = format_address(sender)
    if isinstance(to, (list, tuple)):
        msg["To"] = ", ".join(format_address(addr) for addr in to)
    else:
        msg["To"] = format_address(to)
    msg["Subject"] = Header(subject or "", "utf-8")
    msg["Date"] = formatdate(localtime=True)
    if reply_to:
        msg["Reply-To"] = format_address(reply_to)
    return msg


def attach_text_part(msg: MIMEMultipart, body: str, subtype: str = "plain") -> None:
    """Attach a text part with explicit UTF-8 charset."""
    msg.attach(MIMEText(body, subtype, _charset="utf-8"))


def attach_file(
    msg: MIMEMultipart,
    path: Union[str, os.PathLike],
    mimetype: Optional[str] = None,
) -> None:
    """Attach a file with RFC 2231 filename encoding.

    Detects maintype/subtype via mimetypes.guess_type when mimetype is None.
    Writes Content-Disposition using the (charset, lang, name) tuple form
    so non-ASCII filenames round-trip per RFC 2231.
    """
    p = Path(path)
    with open(p, "rb") as fp:
        content = fp.read()

    if mimetype is None:
        guessed, _ = mimetypes.guess_type(str(p))
        mimetype = guessed or "application/octet-stream"
    maintype, _, subtype = mimetype.partition("/")
    if not subtype:
        maintype, subtype = "application", "octet-stream"

    part = MIMEBase(maintype, subtype)
    part.set_payload(content)
    encoders.encode_base64(part)
    part.add_header(
        "Content-Disposition",
        "attachment",
        filename=("utf-8", "", p.name),
    )
    msg.attach(part)
```

### Key Constraints

- **No `self.logger`** — this module has no `self`. If errors arise (e.g.
  `FileNotFoundError` from `open()` in `attach_file`), let them propagate
  to the caller. The provider classes wrap into `ProviderError`.
- **`Header(None, "utf-8")`** is documented to accept; do not guard with `if
  subject is not None`. Use `subject or ""` for empty-but-not-None safety.
- **`reply_to`** is included because it's a clean drop-in helper; today's
  providers don't set it, but adding the parameter is cheap and forward-
  compatible. If you'd rather keep YAGNI strict, drop the parameter — but
  do not silently swallow it.
- The `to` parameter accepts `str | list[str]`. The base providers today pass
  `to.account.address` (a string) or a `", ".join(...)` of strings — the
  helper unifies both shapes.

### References in Codebase

- `notify/providers/mail.py:142` — current `MIMEMultipart("alternative")` site
  (no UTF-8 policy) that this helper replaces.
- `notify/providers/mail.py:149` — current raw `msg["Subject"] = subject` site.
- `notify/providers/mail.py:170-182` — current `add_attachment` whose RFC 2183
  bug `attach_file` fixes.

---

## Acceptance Criteria

- [ ] `notify/providers/_mime_utils.py` exists and imports cleanly:
      `python -c "from notify.providers import _mime_utils; print(dir(_mime_utils))"`
- [ ] All five public functions present with the exact names and signatures
      listed under "Pattern to Follow".
- [ ] Module has zero `notify.*` imports (`grep -E "from notify|import notify"
      notify/providers/_mime_utils.py` returns nothing).
- [ ] No `async def` in the module (all functions are sync).
- [ ] Module is not exported from `notify/providers/__init__.py`
      (leading-underscore private).
- [ ] `ruff check notify/providers/_mime_utils.py` clean.
- [ ] `mypy notify/providers/_mime_utils.py` clean (or no new errors vs.
      project baseline).

---

## Test Specification

Tests for this helper live in `tests/test_email_utf8.py` and are written in
TASK-006. **Do not** create a separate test file in this task.

The implementing agent MAY do a quick smoke check at the end:

```python
from email.parser import BytesParser
from notify.providers import _mime_utils as mu

msg = mu.build_alternative_message(
    sender="Sr. Ñoño <s@ex.com>",
    to="u@ex.com",
    subject="Reservación ✈️",
)
mu.attach_text_part(msg, "Hola José 🌟")
print(msg.as_string()[:400])  # eyeball: Subject contains =?utf-8?, Content-Type has charset="utf-8"
```

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** at `sdd/specs/NAV-8390-email-utf8.spec.md` — §2
   (Helper API), §3 Module 1, §6 (Codebase Contract), §7 (Known Risks).
2. **No dependencies** — TASK-001 is the foundation.
3. **Verify the Codebase Contract**:
   - `python -c "from email.policy import SMTPUTF8; print(SMTPUTF8)"` — confirm.
   - `python -c "from email.utils import formataddr; print(formataddr.__doc__)"` —
     confirm `charset=` kwarg accepted.
4. **Implement** the module exactly per "Pattern to Follow".
5. **Verify** all acceptance criteria locally.
6. **Move this file** to `sdd/tasks/completed/TASK-001-mime-utils-helper.md`.
7. **Update index** `sdd/tasks/index/NAV-8390-email-utf8.json` → `"done"`.
8. **Fill in the Completion Note** below.

---

## Completion Note

**Completed by**: claude-sonnet-4-6 (SDD Worker)
**Date**: 2026-05-13
**Notes**: Implemented all 5 functions per spec §2 Helper API. Removed
`email_policy` import (unused after decision to not pass
`policy=email.policy.SMTPUTF8` to MIMEMultipart constructor). Python 3.11
EmailPolicy rejects Header objects via its header-factory, breaking RFC 2047
Subject encoding. Used default compat32 policy so `Header(subject, 'utf-8')`
assignment works and produces RFC 2047 encoded-word output.
**Deviations from spec**: `policy=email.policy.SMTPUTF8` NOT passed to
MIMEMultipart constructor (Python 3.11 incompatibility with Header objects).
Default compat32 policy used; RFC 2047 encoding via Header() provides the
required ASCII safety for non-SMTPUTF8 servers (spec §7 Risk #3).
