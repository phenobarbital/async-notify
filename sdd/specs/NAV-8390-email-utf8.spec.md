---
# FEAT-145 flow-type fields.
# Resolved in brainstorm (Q3): patch release as hotfix off main.
type: hotfix
base_branch: main
---

# Feature Specification: UTF-8 handling in email providers (NAV-8390)

**Feature ID**: FEAT-001
**Date**: 2026-05-13
**Author**: Jesus Lara
**Status**: approved
**Target version**: 1.5.6 (hotfix)
**Jira**: NAV-8390 — *error con emails en UTF-8 en notify*

---

## 1. Motivation & Business Requirements

### Problem Statement

Outgoing emails sent through `notify.providers.mail.ProviderEmail` (used by
`Email`, `Aws`), `notify.providers.smtp.SMTP`, and `notify.providers.ses.Ses`
mangle non-ASCII characters in:

1. **Subject** — assigned raw (`msg["Subject"] = subject`). Under the legacy
   `compat32` policy the `email` package falls back to `us-ascii` with `?`
   substitution. Recipients see `Re??servations` instead of `Reservaciones`.
2. **Body parts** — `MIMEText(text, "plain")` and `MIMEText(content, "html")`
   default `_charset` to `us-ascii`; non-ASCII payloads either `?`-substitute
   or raise `UnicodeEncodeError`.
3. **`Content-Type` headers** — written without `charset=utf-8`; receiving
   MUAs may render UTF-8 bytes as Latin-1.
4. **From/To/Sender display names** — same raw assignment, same `?` damage.
5. **Attachment filenames** — `add_attachment(... filename=str(file))` writes
   `Content-Disposition` without RFC 2231 encoding; non-ASCII names mangle.

The Jira reporter named `notify/providers/mail.py:198` as the symptom site. We
verified the root cause is upstream of that `send_message` call — it is in MIME
construction, replicated identically in `notify/providers/smtp/smtp.py` and
`notify/providers/ses/ses.py`.

### Goals

- All three MIME-building providers emit RFC 2047 / RFC 2231 / `charset=utf-8`
  compliant message bytes when handed non-ASCII subjects, bodies, display
  names, or attachment filenames.
- Deduplicate the MIME construction across `mail.py`, `smtp.py`, and `ses.py`
  into a single private helper so the next UTF-8-shaped bug has one fix site.
- Lock the `aiosmtplib` floor in `pyproject.toml` to `>=5.0` to match the
  version the test suite already runs against (currently resolved to 5.1.0 by
  uv against the loose `>=3.0.2`).
- Ship as the 1.5.6 hotfix off `main`.

### Non-Goals (explicitly out of scope)

- `Gmail` and `Outlook` providers — they override `_render_` and never enter
  the MIME path (`Gmail` uses `gmail.Message`, `Outlook` uses MS Graph JSON).
- Migration to `email.message.EmailMessage` (Option C from brainstorm) — real
  modernization win but unnecessary risk for a hotfix. Deferred. See
  `proposals/NAV-8390-email-utf8.brainstorm.md` §Options Explored.
- Adding inline-image / `Content-ID` support, S/MIME, DKIM signing.
- Changing the `ProviderEmail.send(...) / _render_(...) / add_attachment(...)`
  public signatures.
- Accepting `bytes` bodies. Current code assumes `str`; behavior unchanged.

---

## 2. Architectural Design

### Overview

Introduce a single private module `notify/providers/_mime_utils.py`. It
exposes pure functions for UTF-8-safe MIME envelope construction, body part
attachment, address formatting, actor parsing, and file attachment with RFC
2231 filename encoding.

Retrofit the three offending sites (`mail.py._render_`,
`smtp.py._render_`, `ses.py._render_`, plus the two `add_attachment`
methods) to delegate to the helper. Public method signatures
(`_render_`, `_send_`, `send`, `add_attachment`) are preserved, so
`Email`/`Aws` (which inherit base `ProviderEmail` unchanged), and any
external subclasses, keep working with no edits.

Bump `aiosmtplib>=3.0.2` → `aiosmtplib>=5.0` in `pyproject.toml` and
regenerate `uv.lock` in the same hotfix.

### Component Diagram

```
                       ┌──────────────────────────────────────┐
                       │ notify/providers/_mime_utils.py (NEW)│
                       │  build_alternative_message()         │
                       │  attach_text_part()                  │
                       │  attach_file()                       │
                       │  format_address()                    │
                       │  parse_actor()                       │
                       └──────────────┬───────────────────────┘
                                      │ called by
            ┌─────────────────────────┼────────────────────────┐
            │                         │                        │
            ▼                         ▼                        ▼
  notify/providers/mail.py   notify/providers/smtp/smtp.py   notify/providers/ses/ses.py
  ProviderEmail              SMTP (ProviderBase)             Ses (ProviderEmail)
  • _render_                 • _render_                       • _render_  (own MIME)
  • add_attachment           • add_attachment                 • _send_    (SES API)

  Inherited (no edits):
    Email(ProviderEmail)              ← uses ProviderEmail._render_ unchanged
    Aws(ProviderEmail)                ← uses ProviderEmail._render_ unchanged

  Untouched (override MIME path entirely):
    Gmail(ProviderEmail)              → returns gmail.Message
    Outlook(ProviderEmail)            → returns MS Graph send_mail() object
```

### Integration Points

| Existing Component | Integration Type | Notes |
|---|---|---|
| `notify.providers.mail.ProviderEmail` | modifies | `_render_` (lines 133–168) and `add_attachment` (170–182) collapse to ~10 lines each, delegating to helper. `_prepare_message` (112–131) deleted — dead code (resolved Q1). |
| `notify.providers.smtp.SMTP` | modifies | Same retrofit on sync `_render_` (lines 175–210) and `add_attachment` (~212). Note: class name is `SMTP`, not `Smtp`. |
| `notify.providers.ses.Ses` | modifies | Retrofit overridden `_render_` (lines 79–101) — drops its own `MIMEMultipart`/`MIMEText` build and calls the helper. `_send_` path (SES API) unchanged. |
| `notify.providers.email.Email` | depends on | Inherits — no edits; behavior changes via base. |
| `notify.providers.aws.Aws` | depends on | Same — inherits, no edits. |
| `notify.providers.gmail.Gmail` | unaffected | Overrides `_render_` to return `gmail.Message`. |
| `notify.providers.outlook.Outlook` | unaffected | Overrides `_render_` to use Microsoft Graph JSON. |
| `pyproject.toml` | modifies | `aiosmtplib>=3.0.2` → `aiosmtplib>=5.0`. |
| `uv.lock` | regenerates | Resolver already lands on `aiosmtplib==5.1.0`; this is "lock in what we test against". |

### Data Models

No new Pydantic models. Internal helper signatures are plain functions over
stdlib `email.mime.*` types.

### New Public Interfaces

None. The new module is private (leading underscore), and no public
`ProviderEmail` / `SMTP` / `Ses` signature changes.

### Helper API (internal — `notify/providers/_mime_utils.py`)

```python
# All signatures are internal; not exported via __init__.py.

def parse_actor(actor: str) -> tuple[str, str]:
    """Split an actor string ('Name <addr@host>' or 'addr@host') into
    (display_name, address). Returns ('', addr) when no display name.
    Centralizes the parsing today scattered across mail.py / ses.py.
    """

def format_address(actor: str) -> str:
    """Return an RFC-2047-encoded From/To/Sender header value.
    Wraps email.utils.formataddr((name, addr), charset='utf-8').
    """

def build_alternative_message(
    *,
    sender: str,
    to: str | list[str],
    subject: str | None,
    reply_to: str | None = None,
) -> MIMEMultipart:
    """Construct a 'multipart/alternative' envelope with:
      • policy=email.policy.SMTPUTF8
      • Subject wrapped in email.header.Header(subject, 'utf-8')
      • From/To/Sender via format_address (RFC 2047)
      • Date via formatdate(localtime=True)
    """

def attach_text_part(msg: MIMEMultipart, body: str, subtype: str = 'plain') -> None:
    """Attach MIMEText(body, subtype, _charset='utf-8') to the envelope."""

def attach_file(
    msg: MIMEMultipart,
    path: str | os.PathLike[str],
    mimetype: str | None = None,
) -> None:
    """Attach a file with RFC 2231 filename encoding.

    Detects maintype/subtype via mimetypes.guess_type when mimetype is None.
    Writes Content-Disposition with filename=('utf-8', '', name) so non-ASCII
    filenames round-trip.
    """
```

---

## 3. Module Breakdown

### Module 1: `notify/providers/_mime_utils.py` (new)
- **Path**: `notify/providers/_mime_utils.py`
- **Responsibility**: Pure, stdlib-only MIME envelope and body construction
  with UTF-8 correctness baked in. No I/O except `attach_file` which reads
  the attachment payload synchronously (matches today's behavior).
- **Depends on**: stdlib `email.*`, `mimetypes`, `os.path`. No `notify.*`
  imports — keep it leaf-level to avoid cycles.

### Module 2: Retrofit `notify/providers/mail.py`
- **Path**: `notify/providers/mail.py`
- **Responsibility**: Rewrite `ProviderEmail._render_` and
  `ProviderEmail.add_attachment` as thin wrappers over Module 1. Delete the
  unused `_prepare_message` method (resolved Q1 — confirm via grep).
- **Depends on**: Module 1.

### Module 3: Retrofit `notify/providers/smtp/smtp.py`
- **Path**: `notify/providers/smtp/smtp.py`
- **Responsibility**: Same retrofit on the sync variant — `SMTP._render_`
  (line 175) and `SMTP.add_attachment` (line ~212).
- **Depends on**: Module 1.

### Module 4: Retrofit `notify/providers/ses/ses.py`
- **Path**: `notify/providers/ses/ses.py`
- **Responsibility**: Rewrite `Ses._render_` (line 79) to use Module 1 instead
  of building its own `MIMEMultipart`/`MIMEText`. SES `_send_` path
  (`send_raw_email` / `send_templated_email`) is unchanged.
- **Depends on**: Module 1.

### Module 5: Bump `aiosmtplib` floor + relock
- **Path**: `pyproject.toml` (line 38), `uv.lock` (regenerated)
- **Responsibility**: `aiosmtplib>=3.0.2` → `aiosmtplib>=5.0`; run `uv lock`.
- **Depends on**: nothing.

### Module 6: Offline regression test
- **Path**: `tests/test_email_utf8.py` (new)
- **Responsibility**: Build messages with non-ASCII fixture data and assert
  the serialized bytes contain the right encodings. No SMTP server.
- **Depends on**: Modules 1–4.

---

## 4. Test Specification

### Unit Tests
| Test | Module | Description |
|---|---|---|
| `test_build_message_envelope_subject_encoded` | Module 1 | Envelope built with non-ASCII subject yields `Subject: =?utf-8?...?=` in `as_string()`. |
| `test_build_message_envelope_from_encoded` | Module 1 | Sender `"Sr. Ñoño <a@b.com>"` round-trips as RFC 2047 encoded display name. |
| `test_attach_text_part_charset` | Module 1 | Attached plain-text part has `Content-Type: text/plain; charset="utf-8"`. |
| `test_attach_text_part_html_emoji` | Module 1 | HTML part containing emoji serializes without `?` substitution. |
| `test_attach_file_rfc2231_filename` | Module 1 | Non-ASCII attachment filename surfaces as `filename*=utf-8''...` in `Content-Disposition`. |
| `test_attach_file_auto_mimetype` | Module 1 | `.pdf` attachment without explicit `mimetype` detects `application/pdf` via `mimetypes`. |
| `test_parse_actor_with_name` | Module 1 | `"Name <a@b.com>"` → `("Name", "a@b.com")`. |
| `test_parse_actor_bare_addr` | Module 1 | `"a@b.com"` → `("", "a@b.com")`. |
| `test_provider_email_render_uses_helper` | Module 2 | `ProviderEmail._render_` output is byte-equivalent to a direct helper call (smoke test). |
| `test_provider_email_prepare_message_removed` | Module 2 | Importing `ProviderEmail` no longer exposes `_prepare_message` (resolved Q1). |
| `test_smtp_render_uses_helper` | Module 3 | Same byte-equivalence smoke test for sync `SMTP._render_`. |
| `test_ses_render_uses_helper` | Module 4 | `Ses._render_` produces helper-shaped output (await the coroutine in pytest-asyncio). |

### Integration Tests
| Test | Description |
|---|---|
| `test_end_to_end_non_ascii_serialization` | Build a full message via `ProviderEmail._render_` with non-ASCII subject+body+sender+attachment, serialize, then parse with stdlib `email.parser.BytesParser` and assert all fields round-trip cleanly. No SMTP server. |

### Test Data / Fixtures
```python
# tests/test_email_utf8.py
import pytest
from email.parser import BytesParser

@pytest.fixture
def non_ascii_subject() -> str:
    return "Reservación confirmada ✈️"

@pytest.fixture
def non_ascii_body_text() -> str:
    return "Hola José — su reservación está lista. 🌟"

@pytest.fixture
def non_ascii_body_html() -> str:
    return "<p>Hola <b>José</b> — su reservación está lista. 🌟</p>"

@pytest.fixture
def non_ascii_sender() -> str:
    return "Sr. Ñoño <s.nono@example.com>"

@pytest.fixture
def non_ascii_recipient() -> str:
    return "Señora Ümlaut <u.umlaut@example.com>"

@pytest.fixture
def non_ascii_attachment(tmp_path):
    f = tmp_path / "reporte_año.pdf"
    f.write_bytes(b"%PDF-1.4 fake")
    return f
```

The integration test asserts (against `as_bytes()`):
- `Subject:` line begins with `=?utf-8?` (RFC 2047)
- Every `Content-Type:` for a text part contains `charset="utf-8"`
- The body bytes contain the original codepoints UTF-8-encoded (after
  Quoted-Printable decode where applicable)
- `Content-Disposition` for the attachment carries `filename*=utf-8''reporte_a%C3%B1o.pdf`

---

## 5. Acceptance Criteria

> This feature is complete when ALL of the following are true:

- [ ] `notify/providers/_mime_utils.py` exists and exposes the five functions
      listed in §2 with matching signatures.
- [ ] `ProviderEmail._render_` constructs the envelope via
      `_mime_utils.build_alternative_message(...)`; the resulting `MIMEMultipart`
      uses `policy=email.policy.SMTPUTF8`.
- [ ] Every `MIMEText(...)` part attached in `mail.py`, `smtp.py`, and `ses.py`
      passes `_charset="utf-8"` (either directly or via `attach_text_part`).
- [ ] All `Subject` assignments in the three retrofitted providers go through
      `email.header.Header(subject, "utf-8")`.
- [ ] All From/To/Sender header assignments in the retrofitted providers go
      through `format_address` / `email.utils.formataddr(..., charset='utf-8')`.
- [ ] `add_attachment` in `mail.py` and `smtp.py` writes `Content-Disposition`
      using RFC 2231 form (`filename=('utf-8', '', name)`).
- [ ] `notify/providers/mail.py:_prepare_message` (the unused method) is
      deleted (resolved Q1; verified unreferenced via `grep -r '_prepare_message'
      notify/`).
- [ ] `notify/providers/ses/ses.py:Ses._render_` no longer constructs its own
      `MIMEMultipart`; it delegates to the helper (resolved Q2).
- [ ] `pyproject.toml` has `aiosmtplib>=5.0` (resolved Q5 — permissive).
- [ ] `uv.lock` regenerated; `uv sync --frozen` succeeds.
- [ ] `tests/test_email_utf8.py` passes under `pytest -q tests/test_email_utf8.py`.
- [ ] Full suite still passes: `make test` (or `uv run pytest`).
- [ ] No changes to `Gmail` or `Outlook` providers (out of scope verified).
- [ ] No changes to public signatures of `ProviderEmail.send / _render_ / _send_
      / add_attachment` (or the `SMTP` / `Ses` analogues).

---

## 6. Codebase Contract

> **CRITICAL — Anti-Hallucination Anchor**
> This section is the single source of truth for what exists in the codebase.
> Re-verified at spec-write time on `main` @ commit f0c03de + uncommitted brainstorm fix.

### Verified Imports

```python
# Already in use:
from email import encoders                              # mail.py:8, smtp.py:7
from email.mime.multipart import MIMEMultipart          # mail.py:10, smtp.py:9, ses.py:4
from email.mime.base import MIMEBase                    # mail.py:11, smtp.py:10
from email.mime.text import MIMEText                    # mail.py:12, smtp.py:11, ses.py:5
from email.mime.image import MIMEImage                  # mail.py:13, smtp.py:12
from email.utils import formatdate                      # mail.py:14, smtp.py:13
import aiosmtplib                                       # mail.py:16
import smtplib                                          # smtp.py:14
from notify.providers.mail import ProviderEmail        # mail.py used by email/email.py:2, aws/aws.py:7, gmail/gmail.py:11, outlook/outlook.py:11, ses/ses.py:9
from notify.exceptions import ProviderError            # mail.py:18, smtp.py:16
from notify.models import Actor                        # mail.py:17, smtp.py:15, ses.py:10

# To be added by this work — all stdlib, no new runtime deps:
from email.header import Header
from email.utils import formataddr
from email import policy as email_policy
import mimetypes
```

### Existing Class Signatures

```python
# notify/providers/mail.py
class ProviderEmail(ProviderBase, ABC):                                # line 23
    provider_type = ProviderType.EMAIL                                 # line 30
    blocking: str = 'asyncio'                                          # line 31  ← str, not bool
    timeout: int = 60                                                  # line 32
    def __init__(self, *args, **kwargs): ...                           # line 34
    async def close(self): ...                                         # line 44
    async def connect(self, *args, **kwargs): ...                      # line 55
    def is_connected(self): ...                                        # line 106
    def _prepare_message(self, to_address, message, content): ...      # line 112  ← DEAD: never called from send(); to be deleted (resolved Q1)
    async def _render_(self, to=None, message=None, subject=None, **kw): # line 133  ← retrofit target
        msg = MIMEMultipart("alternative")                             # line 142
        msg["Subject"] = subject                                       # line 149  ← raw assign (bug)
        msg.attach(MIMEText(message, "plain"))                         # line 154  ← no _charset (bug)
        msg.add_header("Content-Type", "text/html")                    # line 166  ← no charset (bug)
        msg.attach(MIMEText(content, "html"))                          # line 167  ← no _charset (bug)
    def add_attachment(self, message, filename, mimetype="octect-stream"): ...  # line 170  ← typo preserved: "octect" not "octet"
    async def _send_(self, to, message, subject, **kwargs):            # line 184
        response = await self._server.send_message(msg)                # line 198  ← reporter's pointer
    async def send(self, recipient=None, message=None, subject=None, **kwargs): ...  # line 212
```

```python
# notify/providers/smtp/smtp.py
class SMTP(ProviderBase):                                              # line 28  ← class name is "SMTP" (caps), not "Smtp"
    provider_type = ProviderType.EMAIL                                 # line 35
    blocking: str = 'executor'                                         # line 36  ← differs from ProviderEmail.blocking
    timeout: int = 60                                                  # line 37
    def __init__(self, hostname=None, port=None, username=None, password=None, **kwargs): ...  # line 39
    def _prepare_message(self, to_address, message, content): ...      # line 153  ← also dead in this file? — verify before deletion
    def _render_(self, to, message=None, subject=None, **kwargs):      # line 175  ← retrofit target (sync, NOT async)
        msg = MIMEMultipart("alternative")                             # line 184
        msg["Subject"] = subject                                       # line 191  ← raw assign (bug)
        msg.attach(MIMEText(message, "plain"))                         # line 196  ← no _charset (bug)
        msg.add_header("Content-Type", "text/html")                    # line 208  ← no charset (bug)
        msg.attach(MIMEText(content, "html"))                          # line 209  ← no _charset (bug)
    def add_attachment(self, message, filename, mimetype="octect-stream"): ...  # line ~212  (typo also preserved)
    def _send_(self, to, message, subject, **kwargs):                  # line 226
        response = self._server.send_message(msg)                      # line 240
```

```python
# notify/providers/ses/ses.py
class Ses(ProviderEmail):                                              # line 22
    provider = "amazon_ses"                                            # line 25
    blocking: str = "asyncio"                                          # line 26
    async def connect(self, **kwargs): ...                             # line 68
    async def close(self): ...                                         # line 73
    async def _render_(self, to, message=None, subject=None, **kwargs): # line 79  ← retrofit target — overrides base
        email_msg = MIMEMultipart("alternative")                       # line 95
        email_msg["Subject"] = subject                                 # line 96  ← raw assign (bug)
        email_msg["From"] = self.sender_email                          # line 97  ← raw assign (bug)
        email_msg["To"] = to.account.address                           # line 98  ← raw assign (bug)
        email_msg.attach(MIMEText(content, "plain"))                   # line 99  ← no _charset (bug)
        email_msg.attach(MIMEText(content, "html"))                    # line 100 ← no _charset (bug)
    async def _send_(self, to, message, subject, client=None, **kwargs): ...  # line 103  ← unchanged (SES API path)
```

```python
# Untouched — out of scope, but documented for reviewers:
# notify/providers/gmail/gmail.py
class Gmail(ProviderEmail):                                            # line 17
    async def _render_(self, to, message=None, subject=None, **kwargs): # line 73
        return Message(**email_dict)   # third-party gmail.Message     # line 98

# notify/providers/outlook/outlook.py
class Outlook(ProviderEmail):                                          # line 22
    async def _render_(self, to, message=None, subject=None, **kwargs): # line 136
        content = self.client.me.send_mail(...)  # MS Graph JSON       # line 153
```

### Integration Points

| New Component | Connects To | Via | Verified At |
|---|---|---|---|
| `_mime_utils.build_alternative_message` | `MIMEMultipart`, `email.policy.SMTPUTF8`, `email.header.Header` | direct stdlib calls | stdlib (py 3.6+) |
| `_mime_utils.attach_text_part` | `MIMEText` | direct stdlib call with `_charset='utf-8'` | stdlib (py 3.0+) |
| `_mime_utils.attach_file` | `MIMEBase`, `mimetypes.guess_type`, RFC 2231 filename param | stdlib | stdlib (py 3.0+) |
| `_mime_utils.format_address` | `email.utils.formataddr` | direct stdlib call with `charset='utf-8'` | stdlib (py 3.6+) |
| `ProviderEmail._render_` | `_mime_utils.build_alternative_message` + `attach_text_part` | function call | `notify/providers/mail.py:133-168` (retrofit target) |
| `ProviderEmail.add_attachment` | `_mime_utils.attach_file` | function call | `notify/providers/mail.py:170-182` (retrofit target) |
| `SMTP._render_` | `_mime_utils.build_alternative_message` + `attach_text_part` | function call | `notify/providers/smtp/smtp.py:175-210` (retrofit target) |
| `Ses._render_` | `_mime_utils.build_alternative_message` + `attach_text_part` | function call | `notify/providers/ses/ses.py:79-101` (retrofit target) |

### Key Attributes & Constants

- `ProviderEmail.provider_type` → `ProviderType.EMAIL` (`mail.py:30`)
- `ProviderEmail.blocking` → `'asyncio'` (`mail.py:31`) — **`str`, not `bool`**
- `ProviderEmail.timeout` → `60` (`mail.py:32`)
- `SMTP.blocking` → `'executor'` (`smtp.py:36`) — different shape from base
- `Ses.blocking` → `'asyncio'` (`ses.py:26`)
- Current `aiosmtplib` floor in `pyproject.toml` line 38: `>=3.0.2`
- Installed (resolved by uv): `aiosmtplib==5.1.0`
- The literal default `mimetype="octect-stream"` (note misspelling vs. the
  correct `octet-stream`) appears in both `mail.py:170` and `smtp.py:~212`.
  Helper will use the **correctly spelled** `application/octet-stream` and
  let mimetypes.guess_type override it. Old typo not preserved — see Known
  Risks #2.

### Does NOT Exist (Anti-Hallucination)

- ~~`aiosmtplib.send_message(..., utf8=True)`~~ — no such kwarg in any
  released version (3.x or 5.x). The Jira reporter's first suggestion is
  inaccurate. SMTPUTF8 / 8BITMIME negotiation is automatic from message
  content; we drive it by setting `policy=email.policy.SMTPUTF8` and
  per-part `_charset="utf-8"` on the MIME objects.
- ~~`aiosmtplib.SMTP.send_message(..., utf8=True)`~~ — same as above; not
  on the instance method either.
- ~~`notify.providers.mail._prepare_message` called from `send()`~~ — the
  method is defined at `mail.py:112` but `send()` at `mail.py:235` calls
  `self._prepare_(...)` (on `ProviderBase`), not `_prepare_message`.
  Implementer MUST `grep -r '_prepare_message' notify/` before deleting to
  confirm there is no inheriting caller.
- ~~`notify.providers._mime_utils`~~ — does not exist yet; this spec creates it.
- ~~`notify.providers.smtp.Smtp`~~ — the class is named `SMTP` (all caps).
  The brainstorm narration occasionally used `Smtp`; the spec uses `SMTP`.
- ~~`Aws._render_`~~ — does not exist; `Aws` is a thin subclass that
  inherits `ProviderEmail._render_` unchanged (`aws/aws.py:17-68` has no
  `_render_` definition). Fixing the base fixes `Aws` automatically.

---

## 7. Implementation Notes & Constraints

### Patterns to Follow

- The helper module is **stdlib-only and synchronous**. It has no `notify.*`
  imports — keep it leaf-level to avoid import cycles.
- Match the existing async/sync split: `ProviderEmail._render_` is `async`
  (it awaits template rendering at `mail.py:163` via `render_async`);
  `SMTP._render_` is sync (it calls `render(...)` at `smtp.py:205`). The
  helper itself is sync; the `await` for template rendering stays in the
  caller, not in the helper.
- Logging: where helpers raise, they raise stdlib exceptions
  (`FileNotFoundError`, `ValueError`). Callers in `mail.py` / `smtp.py` /
  `ses.py` are responsible for wrapping into `ProviderError` per their
  existing patterns. Do not introduce `self.logger` inside the helper —
  it has no `self`.
- Preserve template rendering order: text part attached first, HTML
  attached second. MUAs treat the last part of `multipart/alternative` as
  the preferred rendering.

### Known Risks / Gotchas

1. **`smtp.py` and `mail.py` divergence on `msg["sender"]`**. `mail.py:151`
   sets `msg["sender"] = self.actor`; `smtp.py:193` has this line commented
   out. The helper should accept an optional `sender` param. The retrofit
   in each file should preserve its current behavior.
2. **`add_attachment` `mimetype` default typo**: today both files use
   `mimetype="octect-stream"` (sic). The helper uses the correctly spelled
   `application/octet-stream`. This is technically a behavior change at the
   header level, but the misspelled type was never valid per IANA; no MUA
   acts on it. Document in the PR description.
3. **Server lacking SMTPUTF8**: `aiosmtplib` 5.x and `smtplib` fall back to
   8BITMIME if the server doesn't advertise `SMTPUTF8`. Header values
   wrapped by `Header(..., "utf-8")` survive the fallback because RFC 2047
   encoding is ASCII-safe by construction. This is the entire reason for
   `Header()` wrapping over relying on `SMTPUTF8` alone.
4. **Non-ASCII local-part addresses** (e.g. `josé@example.com`): rejected
   by ASCII-only servers. We do nothing special — upstream
   `SMTPRecipientsRefused` bubbles up unchanged.
5. **`bytes` body input**: not supported. Today's code already crashes on
   `bytes`; behavior unchanged.
6. **`Header(None, "utf-8")`** when `subject` is `None`: documented to
   accept; the helper passes through unchanged. Test
   `test_build_message_envelope_subject_encoded` should include a None case.
7. **SES `_send_` accepts `client` kwarg** (`ses.py:108`) which today's
   `Ses._send_` signature accepts but the base does not. Retrofit of
   `Ses._render_` does not touch `_send_`; preserve `client` handling
   intact.
8. **The dirty working tree at spec-write time**: `Makefile`, `pyproject.toml`,
   `docs/requirements-dev.txt` modifications from earlier session work are
   uncommitted and unrelated. The hotfix's `pyproject.toml` edit
   (aiosmtplib bump) must NOT be conflated with those. Resolve the prior
   work in a separate commit/PR.

### External Dependencies

| Package | Version | Reason |
|---|---|---|
| `aiosmtplib` | `>=5.0` (bumped from `>=3.0.2`) | Lock floor to what we test against; 5.x improves SMTPUTF8 / 8BITMIME negotiation; usage surface unchanged from 3.x → 5.x. |
| stdlib `email.header.Header` | py 3.0+ | RFC 2047 Subject encoding. |
| stdlib `email.utils.formataddr` | py 3.6+ for `charset=` | Display-name RFC 2047 encoding. |
| stdlib `email.policy.SMTPUTF8` | py 3.6+ | Per-message UTF-8 policy. |
| stdlib `mimetypes` | py 3.0+ | Attachment maintype/subtype auto-detection. |

No new runtime dependencies. No new dev dependencies.

---

## 8. Open Questions

- [x] Should `notify/providers/mail.py:_prepare_message` (lines 112–131) be
      deleted as part of this fix? — *Resolved in brainstorm Q1*: remove if
      not used. Implementer must run `grep -r '_prepare_message' notify/`
      before deletion to confirm no inheriting caller relies on it.
- [x] Should `notify/providers/ses/ses.py` be audited for the same pattern
      and fixed in the same PR? — *Resolved in brainstorm Q2*: yes, audited.
      `Ses._render_` (line 79) has the identical bug and is in scope; see
      Module 4.
- [x] Should this ship as a `1.5.6` patch release? — *Resolved in brainstorm
      Q3*: yes, ship as **hotfix off `main`**, no new features bundled.
      Spec frontmatter set to `type: hotfix`, `base_branch: main`.
- [x] Centralize parsing of the `actor` string into `parse_actor() ->
      (name, addr)` inside `_mime_utils`? — *Resolved in brainstorm Q4*:
      yes. Helper function specified in §2.
- [x] `aiosmtplib` floor: permissive `>=5.0` or strict `>=5.1`? — *Resolved
      in brainstorm Q5*: permissive `>=5.0`. Reflected in §7.
- [ ] **New (implementer-facing)**: Should `smtp.py:_prepare_message`
      (line 153, if present) also be deleted symmetrically with the
      `mail.py` one? Same `grep` check applies. — *Owner: implementer*
- [ ] **New (release-facing)**: Bump `notify/version.py` to `1.5.6` as part
      of this hotfix, or leave to release tooling? — *Owner: Jesus Lara*: bump version.

---

## Worktree Strategy

- **Default isolation unit**: `per-spec` (all tasks run sequentially in one
  worktree).
- **Rationale**: 6 tasks (helper + 3 retrofits + dep bump + tests), each
  builds on the previous. The retrofits cannot proceed until the helper
  exists; the tests assume the retrofits are in. Splitting buys nothing.
- **Worktree creation** (from `main`, since this is a hotfix):
  ```bash
  git checkout main
  git pull --ff-only origin main
  git worktree add -b hotfix-001-email-utf8 \
    .claude/worktrees/hotfix-001-email-utf8 HEAD
  cd .claude/worktrees/hotfix-001-email-utf8
  ```
- **Cross-feature dependencies**: none. `sdd/specs/` and `sdd/tasks/active/`
  are empty at spec-write time.
- **`/sdd-done` semantics for hotfix** (per `CLAUDE.md`): does NOT push to
  or open a PR against `main`. The PR is user-initiated; after merge, run
  `/sdd-done FEAT-001 --sync-dev` to propagate back to `dev`.

---

## Revision History

| Version | Date | Author | Change |
|---|---|---|---|
| 0.1 | 2026-05-13 | Jesus Lara | Initial draft from NAV-8390 brainstorm. Scope: mail.py + smtp.py + ses.py retrofit + shared `_mime_utils` helper + `aiosmtplib>=5.0` floor bump. All five brainstorm open questions carried forward as `[x]` resolved. |
