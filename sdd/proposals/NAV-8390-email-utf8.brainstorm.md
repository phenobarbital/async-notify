---
# FEAT-145 flow-type fields.
# Bug-only fix touching production email path. Could be reasonably argued either
# way (feature/dev vs hotfix/main). Defaulting to feature/dev — flip to
# hotfix/main if Ops wants this on the next patch release of async-notify.
type: feature
base_branch: dev
jira: NAV-8390
jira_summary: "error con emails en UTF-8 en notify"
jira_type: Bug
jira_priority: Medium
jira_components: []
jira_labels: []
complexity: fix
status: exploration
---

# Brainstorm: Fix UTF-8 handling in email providers (NAV-8390)

**Date**: 2026-05-13
**Author**: Jesus Lara
**Status**: exploration
**Recommended Option**: B

---

## Problem Statement

Outgoing emails sent through `notify.providers.mail.ProviderEmail` (used by `Email`,
`Aws`) and the standalone `notify.providers.smtp.Smtp` provider mangle non-ASCII
characters in:

1. **Subject** — assigned raw (`msg["Subject"] = subject`); the `email` package
   silently encodes it with the default header charset, which for legacy
   `compat32` policy means `us-ascii` with `?` substitution for any non-ASCII
   byte. Recipients see `Re??servations` instead of `Reservaciones`.
2. **Body parts** — `MIMEText(text, "plain")` and `MIMEText(content, "html")`
   default `_charset` to `us-ascii`, so non-ASCII payloads either get replaced
   with `?` or, depending on the SMTP path, raise `UnicodeEncodeError`.
3. **Content-Type headers** — `add_header("Content-Type", "text/plain")` is
   written without `charset=utf-8`, so even when the body bytes are UTF-8 the
   receiving MUA may render them as Latin-1.
4. **From/To/sender display names** — same untouched assignment; non-ASCII names
   break or `?`-substitute.
5. **Attachment filenames** — `add_attachment` uses `filename=str(file)` against
   `Content-Disposition`, which is restricted to ASCII per RFC 2183; non-ASCII
   attachment names get mangled or dropped.

The Jira reporter pinpointed `notify/providers/mail.py:198` as the symptom site.
We verified the root cause is upstream of the `send_message` call — it is in the
MIME construction, replicated identically in `notify/providers/smtp/smtp.py`.

> **Reporter accuracy note**: the reporter suggested `aiosmtplib.send_message(...,
> utf8=True)`. `aiosmtplib` 3.x has no such kwarg — UTF-8 / `SMTPUTF8` negotiation
> is automatic from message content. The actionable half of the suggestion is the
> `email.policy.SMTPUTF8` / charset / `Header(...)` recipe, which we adopt.

## Constraints & Requirements

- **Scope** (user-approved): fix both `notify/providers/mail.py` (async base used
  by `Email`/`Aws`) and `notify/providers/smtp/smtp.py` (sync variant). Extract a
  shared MIME-builder helper to remove the duplication.
- **Out of scope**: `Gmail` (uses third-party `gmail.Message`) and `Outlook`
  (uses Microsoft Graph JSON via `GraphClient.me.send_mail`). They override
  `_render_` and never touch the MIME path.
- **Regression coverage**: add an offline pytest that serializes a message with
  non-ASCII subject, body, sender display name, and attachment filename, then
  asserts the encoded bytes contain a correctly RFC-2047 subject, `charset="utf-8"`
  on each part, and an RFC-2231 `filename*=utf-8''…` parameter. No SMTP server.
- **Extras** (user-approved): encode From/To/sender display-names (RFC 2047 via
  `email.utils.formataddr` with explicit `charset='utf-8'`); use RFC 2231 for
  attachment filenames.
- **Compatibility**: Python 3.9 floor (per `pyproject.toml`); `email.policy.SMTPUTF8`
  and `email.utils.formataddr(..., charset=...)` are available since 3.6.
- **Public API**: prefer no breaking changes to `ProviderEmail.send(...)` /
  `_render_(...)` / `add_attachment(...)` signatures. Internal-only fix.
- **No new runtime dependencies** — stdlib `email.*` is enough.

---

## Options Explored

### Option A: Minimal in-place patch (no helper extraction)

Patch `mail.py` and `smtp.py` directly: pass `_charset="utf-8"` to every
`MIMEText`, wrap `Subject` in `Header(..., "utf-8")`, re-format From/To via
`formataddr(..., charset='utf-8')`, and switch `add_attachment` to RFC 2231
filename encoding. Leave the two files structurally as they are today.

✅ **Pros:**
- Smallest possible diff; lowest review burden.
- Zero refactoring risk to inheriting providers (Email/Aws).
- Trivially backportable to an LTS branch if needed.

❌ **Cons:**
- Bug-class stays duplicated — the next non-ASCII bug (e.g. inline-image
  Content-ID with diacritics, attachment maintype detection) has to be fixed
  twice. We just fixed copy A while copy B silently re-rotted last release.
- The two `_render_` methods diverge in subtle ways already (sync vs async
  template render, `msg["sender"]` only on `mail.py`); leaving them duplicated
  guarantees they keep diverging.
- Misses the user-approved "dedupe" goal.

📊 **Effort:** Low

📦 **Libraries / Tools:**
| Package | Purpose | Notes |
|---|---|---|
| stdlib `email.header.Header` | RFC 2047 Subject encoding | Available since 3.0 |
| stdlib `email.utils.formataddr` | Display-name encoding | `charset=` kwarg since 3.6 |
| stdlib `email.policy.SMTPUTF8` | Optional, applied per-message | Available since 3.6 |

🔗 **Existing Code to Reuse:**
- `notify/providers/mail.py:_render_` — direct edits
- `notify/providers/smtp/smtp.py:_render_` — direct edits

---

### Option B: Extract a shared MIME-builder helper, retrofit both providers (Recommended)

Create `notify/providers/_mime_utils.py` exposing:

- `build_alternative_message(*, sender, to, subject, reply_to=None) -> MIMEMultipart`
  — builds the envelope with `Header(subject, "utf-8")`, `formataddr(..., charset='utf-8')`
  for From/To/Sender, `Date` via `formatdate`, and `policy=email.policy.SMTPUTF8`.
- `attach_text_part(msg, body: str, subtype: str = "plain") -> None`
  — wraps `MIMEText(body, subtype, _charset="utf-8")`.
- `attach_file(msg, path: str | Path, mimetype: str | None = None) -> None`
  — auto-detects via `mimetypes.guess_type`, encodes filename with RFC 2231
  (`add_header("Content-Disposition", "attachment", filename=("utf-8", "", name))`).

Rewrite `mail.py._render_` / `mail.py.add_attachment` and `smtp.py._render_` /
`smtp.py.add_attachment` to thin pass-throughs that call the helpers. Drop the
duplicated `_prepare_message` method (it's defined on `ProviderEmail` but never
called from `send()` — `_render_` shadows it).

✅ **Pros:**
- Matches the user-approved scope exactly: fix both files AND remove the
  duplication so the next UTF-8-shaped bug only needs one fix.
- Preserves the public `_render_` / `_send_` / `add_attachment` signatures, so
  no inheriting provider (`Email`, `Aws`, plus the two overriders `Gmail`,
  `Outlook` that don't touch this path) needs changes.
- Helper is unit-testable in isolation — no SMTP server, no async setup.
- Sets up a clean seam for future enhancements (inline images, signed S/MIME).

❌ **Cons:**
- Larger diff than Option A; one new module to review.
- Smtp.py's sync `_render_` and mail.py's async `_render_` differ in template
  rendering (`.render()` vs `.render_async()`); helper has to accept the
  already-rendered text, leaving the await in the caller. Solvable but a wrinkle.

📊 **Effort:** Low–Medium

📦 **Libraries / Tools:**
| Package | Purpose | Notes |
|---|---|---|
| stdlib `email.mime.multipart.MIMEMultipart` | Envelope construction | unchanged from today |
| stdlib `email.mime.text.MIMEText` | Body parts | called via helper with explicit `_charset="utf-8"` |
| stdlib `email.header.Header` | Subject encoding | wraps non-ASCII subjects |
| stdlib `email.utils.formataddr` | Display-name encoding | `formataddr((name, addr), charset='utf-8')` |
| stdlib `email.policy.SMTPUTF8` | Per-message policy | applied at construction |
| stdlib `mimetypes` | Attachment maintype detection | replaces hardcoded `application/octet-stream` |

🔗 **Existing Code to Reuse:**
- `notify/providers/mail.py:_render_` (lines 133–168) — collapsed to ~10 lines.
- `notify/providers/mail.py:add_attachment` (lines 170–182) — moved to helper.
- `notify/providers/smtp/smtp.py:_render_` (lines 175–210) — collapsed to ~10 lines.
- `notify/providers/smtp/smtp.py:add_attachment` (~line 212) — moved to helper.

---

### Option C: Migrate to modern `email.message.EmailMessage` API

Replace the legacy `email.mime.*` builders with `EmailMessage` constructed under
`policy=email.policy.SMTPUTF8`. `EmailMessage` does Subject/address/filename
encoding automatically; the helper becomes ~30 lines.

✅ **Pros:**
- Most idiomatic for Python 3.6+; stdlib docs explicitly recommend this API
  over `email.mime.*` since 3.6.
- Eliminates manual `Header(...)` / `formataddr(..., charset=...)` calls — the
  policy handles them.
- `EmailMessage.add_attachment(content, maintype=..., subtype=..., filename=...)`
  handles RFC 2231 filename encoding internally.
- Future-proof: when we eventually need DKIM signing or S/MIME, modern API is
  required.

❌ **Cons:**
- Changes the type returned by `_render_` (`MIMEMultipart` → `EmailMessage`).
  Today's overriders (`Gmail`, `Outlook`) don't call into the base's return
  value, so this is theoretically safe — but it is a behavior change that
  external subclassers (if any consumers of `async-notify` exist) would see.
- `EmailMessage.add_attachment` has a different signature than the current
  `add_attachment(message, filename, mimetype)`; preserving the old signature
  means adapter code anyway, so much of the "ergonomic win" is paid back at the
  call site.
- Wider blast radius for what is, strictly, a Medium-priority bug. Risk/reward
  for a single-release fix is unfavorable.

📊 **Effort:** Medium

📦 **Libraries / Tools:**
| Package | Purpose | Notes |
|---|---|---|
| stdlib `email.message.EmailMessage` | Modern message API | Python 3.6+ |
| stdlib `email.policy.SMTPUTF8` | Required policy | identical to Option B |
| stdlib `mimetypes` | Auto-detect maintype/subtype for attachments | identical to Option B |

🔗 **Existing Code to Reuse:**
- Same target sites as Option B, but rewritten rather than wrapped.

---

## Recommendation

**Option B** is recommended because:

- It is the smallest change that hits **all three** of the user's stated goals:
  fix both providers, remove the duplication, and cover the user-added extras
  (address encoding, attachment filename encoding).
- It preserves the public API (`_render_`, `_send_`, `add_attachment`
  signatures), so `Email`, `Aws`, and any external subclasses keep working
  without edits.
- The helper is plain, synchronous, no-I/O, and trivially unit-testable — which
  satisfies the user-chosen offline-MIME-assertion test approach without
  needing aiosmtpd or pytest-asyncio gymnastics.
- Option C's "modern API" win is real but does not fix any UTF-8 case that
  Option B doesn't already fix. We can revisit C as a follow-up refactor once
  the leak is plugged.

Trade-off accepted: we keep the legacy `MIMEMultipart` API instead of moving to
`EmailMessage`. The cost is one extra `Header(...)` wrap and one explicit
`_charset="utf-8"` per part — paid once, inside the helper, where it stays
hidden from callers.

**Acceptance-criteria coverage (Jira has no AC field; criteria distilled from
the description + extras agreed in Q&A):**

| Criterion | Covered by Option B? |
|---|---|
| `aiosmtplib.send_message` / `SMTP.send_message` emits UTF-8 message bytes | ✅ via `policy=SMTPUTF8` on the MIME envelope |
| `MIMEMultipart` constructed with UTF-8 policy | ✅ |
| `Content-Type: text/plain; charset=utf-8` on every part | ✅ via `MIMEText(..., _charset="utf-8")` |
| `Subject` encoded via `email.header.Header(subject, "utf-8")` | ✅ |
| From/To/sender display-names UTF-8 safe | ✅ via `formataddr((name, addr), charset='utf-8')` |
| Attachment filenames UTF-8 safe (RFC 2231) | ✅ via `add_header("Content-Disposition", "attachment", filename=("utf-8","",name))` |
| Both `mail.py` and `smtp.py` fixed via shared helper | ✅ |
| Offline regression test in place | ✅ |

---

## Feature Description

### User-Facing Behavior

A caller sending an email through `Email`, `Aws`, or `Smtp` providers with any
of the following in scope:

- A subject containing non-ASCII characters (`"Reservación confirmada ✈️"`)
- A body (text or HTML) containing non-ASCII characters or emoji
- A sender or recipient address with a non-ASCII display name
  (`"Sr. Ñoño <s.nono@example.com>"`)
- An attachment whose filename contains non-ASCII characters
  (`"reporte_año.pdf"`)

…will see the email delivered with all characters intact, rendered correctly in
modern MUAs (Gmail web/iOS, Outlook 365, Apple Mail, Thunderbird), and with the
attachment opening under its original filename.

No changes to the calling code are required — the fix is internal.

### Internal Behavior

1. `ProviderEmail.send(...)` / `Smtp.send(...)` invokes `_render_(...)` as today.
2. `_render_` now calls `_mime_utils.build_alternative_message(...)` to construct
   the envelope. The helper:
   - Creates a `MIMEMultipart("alternative", policy=email.policy.SMTPUTF8)`.
   - Sets `From`, `To`, `Sender` via `formataddr` with `charset='utf-8'`.
   - Sets `Subject` via `email.header.Header(subject, "utf-8")`.
   - Sets `Date` via `formatdate(localtime=True)` (unchanged).
3. `_render_` calls `_mime_utils.attach_text_part(msg, text, "plain")` and
   `attach_text_part(msg, html, "html")`. Each helper call constructs
   `MIMEText(body, subtype, _charset="utf-8")`.
4. When attachments are supplied, `add_attachment` delegates to
   `_mime_utils.attach_file(msg, path, mimetype)`, which detects the maintype/
   subtype via `mimetypes.guess_type`, base64-encodes the payload, and writes the
   `Content-Disposition` header using the RFC 2231 form so non-ASCII filenames
   round-trip.
5. `aiosmtplib.SMTP.send_message(msg)` (and `smtplib.SMTP.send_message(msg)` for
   the sync variant) then auto-negotiates `8BITMIME` / `SMTPUTF8` against the
   server. With the message bytes correctly tagged, this path "just works".

### Edge Cases & Error Handling

- **Server lacks `SMTPUTF8`**: `aiosmtplib`/`smtplib` falls back to `8BITMIME`
  encoding; the headers are still RFC 2047 quoted-printable from `Header(...)`,
  so non-ASCII headers survive even on legacy servers. This is the entire reason
  for `Header()` wrapping (vs. relying on `SMTPUTF8` alone).
- **Recipient address contains non-ASCII local-part (e.g. `josé@example.com`)**:
  pure-ASCII servers will reject. We do nothing special — the upstream
  `SMTPRecipientsRefused` exception bubbles up, same as today.
- **Subject is `None` or empty**: helper passes through unchanged; `Header(None,
  "utf-8")` is documented to accept empty.
- **Body is `bytes`**: out of scope — current code assumes `str`; we keep that
  contract. If a caller passes bytes today they already crash; behavior unchanged.
- **Mixed text+html template path**: identical control flow to today (text part
  attached first, html second). Order matters for MUA preference.
- **Attachment file missing**: the helper raises `FileNotFoundError` — same as
  today (no behavior change).

---

## Capabilities

### New Capabilities
- `email-utf8-encoding`: shared MIME-builder helper providing UTF-8-safe envelope,
  body, address, subject, and attachment-filename encoding for SMTP-based email
  providers.

### Modified Capabilities
- `provider-email-base` (`notify/providers/mail.py`): `_render_` and
  `add_attachment` rewritten as thin wrappers over the new helper.
- `provider-smtp` (`notify/providers/smtp/smtp.py`): same retrofit on the sync
  path.

---

## Impact & Integration

| Affected Component | Impact Type | Notes |
|---|---|---|
| `notify/providers/mail.py` | modifies | `_render_` (lines 133–168) and `add_attachment` (170–182) collapsed to helper calls. `_prepare_message` (112–131) likely deletable — appears dead. |
| `notify/providers/smtp/smtp.py` | modifies | Same retrofit on sync `_render_` (175–210) and `add_attachment` (~212). |
| `notify/providers/_mime_utils.py` | adds | New private helper module; not exported. |
| `notify/providers/email/email.py` | depends on | Inherits — no edits, but covered by regression test. |
| `notify/providers/aws/aws.py` | depends on | Same — inherits, no edits. |
| `notify/providers/gmail/gmail.py` | unaffected | Overrides `_render_`, uses `gmail.Message`. |
| `notify/providers/outlook/outlook.py` | unaffected | Overrides `_render_`, uses Microsoft Graph JSON. |
| `tests/test_email_utf8.py` | adds | Offline pytest covering subject, body, addresses, attachment filename. |

No new runtime dependencies. No `pyproject.toml` change. No config or
deployment change.

---

## Code Context

### User-Provided Code

```text
# Source: Jira NAV-8390 description (user-provided suggestion)
# en notify/providers/mail.py:198 debería pasarle utf8=True a
# aiosmtplib.send_message, o construir el MIMEMultipart con
# policy=email.policy.SMTPUTF8 y asegurar Content-Type: text/plain; charset=utf-8
# en cada part + Subject codificado vía email.header.Header(subject, "utf-8").
```

(The MIME-side half of this suggestion is adopted. The `utf8=True` kwarg on
`aiosmtplib.send_message` does not exist in v3.x — see Anti-Hallucination
section.)

### Verified Codebase References

#### Classes & Signatures

```python
# From notify/providers/mail.py
class ProviderEmail(ProviderBase, ABC):                                  # line 23
    provider_type = ProviderType.EMAIL                                   # line 30
    blocking: str = 'asyncio'                                            # line 31
    timeout: int = 60                                                    # line 32

    def __init__(self, *args, **kwargs): ...                             # line 34
    async def close(self): ...                                           # line 44
    async def connect(self, *args, **kwargs): ...                        # line 55
    def is_connected(self): ...                                          # line 106
    def _prepare_message(self, to_address, message, content): ...        # line 112  (likely dead)
    async def _render_(self, to=None, message=None, subject=None, **kw): # line 133
        msg = MIMEMultipart("alternative")                               # line 142
        msg["Subject"] = subject                                         # line 149  ← raw assign
        msg.attach(MIMEText(message, "plain"))                           # line 154  ← no charset
        msg.add_header("Content-Type", "text/html")                      # line 166  ← no charset
        msg.attach(MIMEText(content, "html"))                            # line 167  ← no charset
    def add_attachment(self, message, filename, mimetype="octect-stream"): ...  # line 170
    async def _send_(self, to, message, subject, **kwargs):              # line 184
        response = await self._server.send_message(msg)                  # line 198  ← reporter's pointer
    async def send(self, recipient=None, message=None, subject=None, **kwargs): ...  # line 212
```

```python
# From notify/providers/smtp/smtp.py  (same bug, sync variant)
def _render_(self, to, message=None, subject=None, **kwargs):            # line 175
    msg = MIMEMultipart("alternative")                                   # line 184
    msg["Subject"] = subject                                             # line 191  ← raw assign
    msg.attach(MIMEText(message, "plain"))                               # line 196  ← no charset
    msg.add_header("Content-Type", "text/html")                          # line 208  ← no charset
    msg.attach(MIMEText(content, "html"))                                # line 209  ← no charset
def _send_(self, to, message, subject, **kwargs):                        # line 226
    response = self._server.send_message(msg)                            # line 240  ← analogous to mail.py:198
```

```python
# Overriders that DO NOT touch MIME path — out of scope for this fix:
# notify/providers/gmail/gmail.py
class Gmail(ProviderEmail):                                              # line 17
    async def _render_(self, to, message=None, subject=None, **kwargs):  # line 73
        return Message(**email_dict)   # third-party gmail.Message       # line 98

# notify/providers/outlook/outlook.py
class Outlook(ProviderEmail):                                            # line 22
    async def _render_(self, to, message=None, subject=None, **kwargs):  # line 136
        content = self.client.me.send_mail(...)  # MS Graph JSON         # line 153
```

#### Verified Imports

```python
# These imports have been confirmed to work:
from email import encoders                              # mail.py:8
from email.mime.multipart import MIMEMultipart          # mail.py:10
from email.mime.base import MIMEBase                    # mail.py:11
from email.mime.text import MIMEText                    # mail.py:12
from email.mime.image import MIMEImage                  # mail.py:13
from email.utils import formatdate                      # mail.py:14
import aiosmtplib                                       # mail.py:16
from notify.providers.mail import ProviderEmail        # used by email/, aws/, gmail/, outlook/

# To be added by this work (all stdlib, no new deps):
from email.header import Header
from email.utils import formataddr
from email import policy as email_policy
import mimetypes
```

#### Key Attributes & Constants

- `ProviderEmail.provider_type` → `ProviderType.EMAIL` (mail.py:30)
- `ProviderEmail.blocking` → `'asyncio'` (mail.py:31) — note: string, not bool
- `ProviderEmail.timeout` → `60` (mail.py:32)
- `Smtp.blocking` → `True` (gmail.py:28 — `bool`; different shape than base)
- `aiosmtplib` version floor in `pyproject.toml`: `>=3.0.2`

### Does NOT Exist (Anti-Hallucination)

- ~~`aiosmtplib.send_message(..., utf8=True)`~~ — no such kwarg exists in
  `aiosmtplib` 3.x. The reporter's first suggestion is inaccurate. UTF-8 / SMTPUTF8
  negotiation is automatic from message content; we control it by setting
  `policy=email.policy.SMTPUTF8` and per-part `_charset="utf-8"` on the
  `MIMEMultipart`/`MIMEText` objects we hand to `send_message`.
- ~~`aiosmtplib.SMTP.send_message(..., utf8=True)`~~ — same as above; not on
  the SMTP client instance either.
- ~~`notify.providers.mail._prepare_message` called from `send()`~~ — defined at
  mail.py:112 but never invoked (the `send()` flow at line 235 calls
  `self._prepare_(...)` on `ProviderBase`, not `_prepare_message`). Likely dead
  code; safe to delete during this fix, but verify with grep before touching.
- ~~`notify.providers._mime_utils`~~ — does not exist yet; this brainstorm
  proposes its creation.

---

## Parallelism Assessment

- **Internal parallelism**: Low. Single feature, two files touched, one new
  helper, one test file. ~3 sequential tasks (create helper, retrofit mail.py +
  smtp.py, add tests). Not worth splitting.
- **Cross-feature independence**: Touches only the email provider tree
  (`notify/providers/mail.py`, `notify/providers/smtp/`, plus a new private
  helper). No overlap with anything currently in flight in this repo (zero
  active specs at the time of writing — `sdd/specs/` and `sdd/tasks/active/`
  are empty).
- **Recommended isolation**: `per-spec`.
- **Rationale**: Standard SDD worktree (`feat/email-utf8`) off `dev`, sequential
  tasks within. Nothing else is contending for these files.

---

## Open Questions

- [ ] Should `notify/providers/mail.py:_prepare_message` (lines 112–131) be
  deleted as part of this fix? It appears unreferenced — `send()` calls
  `_prepare_` (from `ProviderBase`), not `_prepare_message`. Confirm via grep
  before removing. — *Owner: implementer*
- [ ] Do we want `notify/providers/ses/` (separate SES provider, if present)
  audited for the same pattern in the same PR, or kept as a follow-up?
  (`tests/test_ses.py` exists; the provider lives elsewhere.) — *Owner: Jesus Lara*
- [ ] Should the fix ship via a `1.5.6` patch release or wait for the next
  feature batch? Affects whether `type:` flips to `hotfix` and `base_branch:` to
  `main`. — *Owner: Jesus Lara*
- [ ] Display-name encoding: should we centralize parsing of the `actor`
  attribute (currently a string like `"Name <addr@host>"` mixed with bare
  emails) into a single `parse_actor() -> (name, addr)` helper inside
  `_mime_utils`, or keep `actor` as opaque-string and only wrap addresses we
  already know are structured? — *Owner: implementer*
