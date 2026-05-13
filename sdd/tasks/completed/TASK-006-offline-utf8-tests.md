# TASK-006: Add offline UTF-8 regression test suite

**Feature**: FEAT-001 — UTF-8 handling in email providers (NAV-8390)
**Spec**: `sdd/specs/NAV-8390-email-utf8.spec.md`
**Status**: pending
**Priority**: high
**Estimated effort**: M (2–4h)
**Depends-on**: TASK-001, TASK-002, TASK-003, TASK-004
**Assigned-to**: unassigned

---

## Context

Without regression coverage, the next refactor in this file family can
silently re-introduce the bug we just fixed (the pattern is duplicated
across three files for a reason — humans copy-paste it). This task adds
the offline pytest suite that locks in UTF-8 correctness.

The test is **offline**: no SMTP server, no aiosmtpd. It builds messages,
serializes them, and parses the bytes back with stdlib `email.parser` to
assert encodings are correct end-to-end. Resolved Q in user Q&A: offline
MIME assertion.

Implements Spec §3 Module 6, §4 Test Specification.

---

## Scope

- Create `tests/test_email_utf8.py` with the 12 unit tests + 1 integration
  test enumerated in spec §4.
- Tests must run with vanilla `pytest` — no extra plugins beyond what's
  already in `[project.optional-dependencies] dev` (pytest-asyncio is
  available for the SES async test).
- Use stdlib `email.parser.BytesParser` to round-trip serialized bytes
  through a parser and assert decoded values are byte-identical to inputs.
- Cover all four affected sites: helper functions directly,
  `ProviderEmail._render_` (mail.py), `SMTP._render_` (smtp.py),
  `Ses._render_` (ses.py).
- Add a small `conftest.py` fixture block if needed for shared non-ASCII
  fixture strings, OR inline them in the test file. Either is fine.

**NOT in scope**:
- Live SMTP integration tests (separate effort, would need aiosmtpd).
- Testing `Gmail` or `Outlook` (spec §1 Non-Goals).
- Performance benchmarks.
- Testing the AWS SES `_send_` path (mocked SES would belong in a separate
  test file).

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `tests/test_email_utf8.py` | CREATE | The 12 unit tests + 1 integration test. |

---

## Codebase Contract (Anti-Hallucination)

### Verified Imports

```python
# Stdlib + project — verified at spec-write time:
import pytest                                          # via dev extra
from email.parser import BytesParser
from email.policy import default as policy_default
from pathlib import Path

# From TASK-001:
from notify.providers import _mime_utils as mu

# From TASK-002 (post-retrofit):
from notify.providers.mail import ProviderEmail

# From TASK-003 (post-retrofit):
from notify.providers.smtp.smtp import SMTP             # class is "SMTP", not "Smtp"

# From TASK-004 (post-retrofit):
from notify.providers.ses.ses import Ses                # async _render_
from notify.models import Actor                         # for crafting recipient fixtures
```

### Existing Signatures to Use

```python
# notify/providers/_mime_utils.py (TASK-001):
def parse_actor(actor: str) -> tuple[str, str]: ...
def format_address(actor: str) -> str: ...
def build_alternative_message(*, sender, to, subject, reply_to=None) -> MIMEMultipart: ...
def attach_text_part(msg, body, subtype='plain') -> None: ...
def attach_file(msg, path, mimetype=None) -> None: ...

# notify/providers/mail.py post-TASK-002:
class ProviderEmail(ProviderBase, ABC):
    # Note: ProviderEmail is ABC; cannot instantiate directly.
    # Use a concrete subclass like Email or Aws, OR a minimal test subclass:
    #
    #   class _StubEmail(ProviderEmail):
    #       provider = "stub"
    #       async def _send_(self, *a, **kw): ...
    #
    # The integration test calls await stub._render_(...) and inspects the
    # returned MIMEMultipart.

# notify/providers/smtp/smtp.py post-TASK-003:
class SMTP(ProviderBase):
    def _render_(self, to, message=None, subject=None, **kwargs) -> MIMEMultipart: ...
    # SYNC — no await.

# notify/providers/ses/ses.py post-TASK-004:
class Ses(ProviderEmail):
    async def _render_(self, to, message=None, subject=None, **kwargs) -> MIMEMultipart: ...
    # Needs sender_email set in __init__; provide a stub Actor.
```

```python
# notify/models.Actor — verified at notify/models/  (re-grep to confirm
# the exact module path before importing; if Actor lives at notify.models
# it imports fine via `from notify.models import Actor`).
#
# Minimum shape needed: `to.account.address` must be a usable string.
# If Actor's full constructor is heavy, create a lightweight namespace stand-in:
#
#   from types import SimpleNamespace
#   recipient = SimpleNamespace(account=SimpleNamespace(address="u@ex.com"))
#
# This works because _render_ only reads to.account.address.
```

### Does NOT Exist

- ~~`pytest.mark.utf8`~~ — no custom marker. Use plain functions or classes.
- ~~`notify.testing` test helpers~~ — no test utilities module exists.
  Build fixtures inline.
- ~~`MIMEText` exposed by `_mime_utils`~~ — the helper module does not
  re-export raw `MIMEText`; tests should call helper functions, not poke
  at MIMEText directly.
- ~~`pyproject.toml [tool.pytest.ini_options] addopts = ["--strict-config",
  "--strict-markers"]`~~ already requires strict markers, so do **not**
  invent custom `@pytest.mark.*` markers.
- ~~`tests/conftest.py`~~ — currently does not exist at repo root for
  notify (verify with `ls tests/conftest.py`). If you need shared
  fixtures, EITHER create a minimal conftest.py OR inline fixtures in
  the test file.

---

## Implementation Notes

### Pattern to Follow

```python
# tests/test_email_utf8.py
"""Offline regression suite for FEAT-001 (NAV-8390).

Builds MIME messages with non-ASCII content, serializes them, parses the
bytes back, and asserts the encoding is correct. No SMTP server.
"""
from types import SimpleNamespace
from email.parser import BytesParser
from email.policy import default as policy_default
from pathlib import Path

import pytest

from notify.providers import _mime_utils as mu


# ---------------------------------------------------------------- fixtures
NON_ASCII_SUBJECT = "Reservación confirmada ✈️"
NON_ASCII_BODY    = "Hola José — su reservación está lista. 🌟"
NON_ASCII_HTML    = "<p>Hola <b>José</b> — su reservación está lista. 🌟</p>"
NON_ASCII_SENDER  = "Sr. Ñoño <s.nono@example.com>"
NON_ASCII_RCPT    = "Señora Ümlaut <u.umlaut@example.com>"


@pytest.fixture
def actor():
    """Lightweight Actor stand-in. _render_ only reads to.account.address."""
    return SimpleNamespace(account=SimpleNamespace(address="u@example.com"))


@pytest.fixture
def non_ascii_attachment(tmp_path):
    f = tmp_path / "reporte_año.pdf"
    f.write_bytes(b"%PDF-1.4 fake")
    return f


# ---------------------------------------------------------- helper-direct tests

def test_parse_actor_with_name():
    name, addr = mu.parse_actor("Name <a@b.com>")
    assert name == "Name"
    assert addr == "a@b.com"


def test_parse_actor_bare_addr():
    name, addr = mu.parse_actor("a@b.com")
    assert name == ""
    assert addr == "a@b.com"


def test_build_message_envelope_subject_encoded():
    msg = mu.build_alternative_message(
        sender=NON_ASCII_SENDER, to="u@example.com", subject=NON_ASCII_SUBJECT,
    )
    raw = msg.as_bytes()
    # Subject must appear as RFC-2047 encoded-word, not raw bytes:
    assert b"Subject: =?utf-8?" in raw
    # Round-trip parse: decoded subject equals input.
    parsed = BytesParser(policy=policy_default).parsebytes(raw)
    assert parsed["Subject"] == NON_ASCII_SUBJECT


def test_build_message_envelope_from_encoded():
    msg = mu.build_alternative_message(
        sender=NON_ASCII_SENDER, to="u@example.com", subject="hi",
    )
    parsed = BytesParser(policy=policy_default).parsebytes(msg.as_bytes())
    # parsed["From"] preserves the display name verbatim.
    assert "Sr. Ñoño" in str(parsed["From"])
    assert "s.nono@example.com" in str(parsed["From"])


def test_build_message_envelope_subject_none():
    """Header(None, ...) is documented; helper must tolerate None subject."""
    msg = mu.build_alternative_message(
        sender="a@b.com", to="u@example.com", subject=None,
    )
    assert msg.as_bytes()  # serializes without raising


def test_attach_text_part_charset():
    msg = mu.build_alternative_message(sender="a@b", to="u@b", subject="x")
    mu.attach_text_part(msg, NON_ASCII_BODY, "plain")
    raw = msg.as_bytes()
    assert b'Content-Type: text/plain; charset="utf-8"' in raw


def test_attach_text_part_html_emoji_roundtrip():
    msg = mu.build_alternative_message(sender="a@b", to="u@b", subject="x")
    mu.attach_text_part(msg, NON_ASCII_HTML, "html")
    parsed = BytesParser(policy=policy_default).parsebytes(msg.as_bytes())
    body = parsed.get_body(preferencelist=("html",)).get_content()
    assert "José" in body
    assert "🌟" in body


def test_attach_file_rfc2231_filename(non_ascii_attachment):
    msg = mu.build_alternative_message(sender="a@b", to="u@b", subject="x")
    mu.attach_file(msg, non_ascii_attachment)
    raw = msg.as_bytes()
    # RFC 2231: filename*=utf-8''<percent-encoded>
    assert b"filename*=utf-8''" in raw
    # Percent-encoding of 'ñ' (U+00F1) is %C3%B1
    assert b"reporte_a%C3%B1o.pdf" in raw


def test_attach_file_auto_mimetype(tmp_path):
    f = tmp_path / "report.pdf"
    f.write_bytes(b"%PDF-1.4")
    msg = mu.build_alternative_message(sender="a@b", to="u@b", subject="x")
    mu.attach_file(msg, f)  # no explicit mimetype
    raw = msg.as_bytes()
    assert b"Content-Type: application/pdf" in raw


# ---------------------------------------------------------- provider retrofit tests

@pytest.mark.asyncio
async def test_provider_email_render_uses_helper(actor):
    """ProviderEmail._render_ produces a UTF-8-safe message via the helper."""
    # Minimal concrete subclass for instantiation.
    class _Stub(ProviderEmail):
        provider = "stub"
        async def _send_(self, *a, **kw):
            return None

    stub = _Stub()
    stub.actor = NON_ASCII_SENDER
    stub._template = None
    msg = await stub._render_(to=actor, message=NON_ASCII_BODY, subject=NON_ASCII_SUBJECT)
    raw = msg.as_bytes()
    assert b"Subject: =?utf-8?" in raw
    assert b'charset="utf-8"' in raw


def test_provider_email_prepare_message_removed():
    """Resolved Q1 (spec §8): dead method deleted."""
    from notify.providers.mail import ProviderEmail
    assert not hasattr(ProviderEmail, "_prepare_message"), \
        "_prepare_message must be removed by TASK-002"


def test_smtp_prepare_message_removed():
    """Resolved second new Q (spec §8): symmetric deletion."""
    from notify.providers.smtp.smtp import SMTP
    assert not hasattr(SMTP, "_prepare_message"), \
        "_prepare_message must be removed by TASK-003"


def test_smtp_render_uses_helper(actor):
    """Sync SMTP._render_ produces a UTF-8-safe message."""
    # Build via the public class. Avoid network: don't call connect/send.
    smtp = SMTP(hostname="localhost", port=25,
                username="u", password="p")
    smtp.actor = NON_ASCII_SENDER  # in case the retrofit reads .actor
    smtp._template = None
    msg = smtp._render_(to=actor, message=NON_ASCII_BODY, subject=NON_ASCII_SUBJECT)
    raw = msg.as_bytes()
    assert b"Subject: =?utf-8?" in raw
    assert b'charset="utf-8"' in raw


@pytest.mark.asyncio
async def test_ses_render_uses_helper(actor):
    """Ses._render_ (async, overridden) produces a UTF-8-safe message."""
    ses = Ses(
        aws_access_key_id="x", aws_secret_access_key="y",
        aws_region_name="us-east-1", sender_email=NON_ASCII_SENDER,
    )
    ses._template = None
    msg = await ses._render_(to=actor, message=NON_ASCII_BODY, subject=NON_ASCII_SUBJECT)
    raw = msg.as_bytes()
    assert b"Subject: =?utf-8?" in raw
    assert b'charset="utf-8"' in raw


# ---------------------------------------------------------- end-to-end integration

@pytest.mark.asyncio
async def test_end_to_end_non_ascii_serialization(actor, non_ascii_attachment):
    """Full pipeline: build, attach text+html+file, serialize, reparse, verify."""
    class _Stub(ProviderEmail):
        provider = "stub"
        async def _send_(self, *a, **kw): return None
    stub = _Stub()
    stub.actor = NON_ASCII_SENDER
    stub._template = None

    msg = await stub._render_(to=actor, message=NON_ASCII_BODY, subject=NON_ASCII_SUBJECT)
    stub.add_attachment(message=msg, filename=str(non_ascii_attachment))

    raw = msg.as_bytes()
    parsed = BytesParser(policy=policy_default).parsebytes(raw)

    assert parsed["Subject"] == NON_ASCII_SUBJECT
    assert "Sr. Ñoño" in str(parsed["From"])

    body = parsed.get_body(preferencelist=("plain",)).get_content()
    assert "José" in body

    # Find the attachment part and check the filename round-trips.
    attachments = [p for p in parsed.walk()
                   if p.get_content_disposition() == "attachment"]
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "reporte_año.pdf"
```

### Key Constraints

- The Stub subclass for `ProviderEmail` is the simplest legal subclass.
  Don't over-engineer it. Inline it in each test, or fold into a
  conftest fixture if you find it repeated.
- `pytest-asyncio` is in the `dev` extra (see `pyproject.toml`'s
  `pytest-asyncio>=0.24.0`). Use `@pytest.mark.asyncio` on async tests.
  Verify the asyncio mode in pyproject — if `asyncio_mode = "auto"` is
  set, the marker is optional but harmless.
- Use stdlib `BytesParser(policy=policy_default)` for round-trip parsing
  — gives a modern message with decoded headers and `.get_body()` helpers.
- Don't rely on exact byte-equality across runs (multipart boundaries are
  random). Use substring `in` checks and parsed-header equality.
- `assert b"reporte_a%C3%B1o.pdf" in raw` assumes percent-encoded ñ. If
  the implementation uses a different (still RFC-compliant) encoding,
  loosen the check to parse `Content-Disposition` and read the decoded
  filename.
- The SES test does NOT need real AWS credentials. The `Ses.__init__`
  accepts dummy strings; `_render_` doesn't touch the network.
- The `pyproject.toml`'s `[tool.pytest.ini_options]` includes
  `filterwarnings = ["error", ...]` — any DeprecationWarning will fail
  the test. If your asserts trip a warning, fix the call site (probably
  in the helper) rather than silencing the warning.

### References in Codebase

- `tests/test_outlook.py`, `tests/test_outlook1.py`, `tests/test_ses.py`
  — look at how existing tests instantiate providers and stub credentials.
- `pyproject.toml:133-138` — `[tool.pytest.ini_options]` settings; respect
  `--strict-markers` and `filterwarnings = ["error", …]`.

---

## Acceptance Criteria

- [ ] `tests/test_email_utf8.py` exists.
- [ ] `pytest -q tests/test_email_utf8.py` runs all 13 tests; all pass.
- [ ] No warnings raised (suite must pass under `filterwarnings =
      ["error", ...]`).
- [ ] `ruff check tests/test_email_utf8.py` clean.
- [ ] Tests cover all four targets per spec §4:
      - helper functions (parse_actor, format_address, build_alternative_message,
        attach_text_part, attach_file)
      - ProviderEmail._render_ (mail.py)
      - SMTP._render_ (smtp.py)
      - Ses._render_ (ses.py)
- [ ] Both `_prepare_message` deletions are asserted
      (mail.py + smtp.py).
- [ ] Full project test suite (`make test` or `uv run pytest`) still passes
      — the new tests don't break unrelated coverage.

---

## Test Specification

This task IS the test specification. Implementer just runs `pytest -q
tests/test_email_utf8.py` to verify.

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** at `sdd/specs/NAV-8390-email-utf8.spec.md` — §4 (Test
   Specification), §6 (Codebase Contract).
2. **Verify dependencies** — all of TASK-001/002/003/004 must be in
   `sdd/tasks/completed/`. The retrofitted code must already exist.
3. **Verify the Codebase Contract** — re-grep `_prepare_message` (must
   be unreferenced) and re-read `_mime_utils.py` for exact signatures.
4. **Check the asyncio mode** in `pyproject.toml` `[tool.pytest.ini_options]`.
   Adjust `@pytest.mark.asyncio` decorators based on the mode.
5. **Implement** all 13 tests per the pattern above.
6. **Verify** every acceptance criterion locally.
7. **Move this file** to `sdd/tasks/completed/TASK-006-offline-utf8-tests.md`.
8. **Update index** → `"done"`.
9. **Fill in the Completion Note** below.

---

## Completion Note

**Completed by**: claude-sonnet-4-6 (SDD Worker)
**Date**: 2026-05-13
**Notes**: All 15 tests pass (spec called for 13 unit + 1 integration = 14;
13th unit test was split as test_smtp_prepare_message_removed makes 15 total).
pytest.ini has asyncio_mode=auto so @pytest.mark.asyncio is optional but kept
for clarity. test_smtp_render_uses_helper must be async because ProviderBase
__init__ calls asyncio.get_running_loop(). Fixed msg.preamble to empty string
in mail.py and smtp.py (non-ASCII preamble caused as_bytes() UnicodeEncodeError).
**Deviations from spec**: test_smtp_render_uses_helper decorated with
@pytest.mark.asyncio (spec showed it as sync, but ProviderBase.__init__
requires a running event loop). preamble fix in mail.py and smtp.py included
in this task's commit (discovered during testing).
