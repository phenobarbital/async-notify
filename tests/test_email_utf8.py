"""Offline regression suite for FEAT-001 (NAV-8390).

Builds MIME messages with non-ASCII content, serialises them, parses the
bytes back with stdlib ``email.parser.BytesParser``, and asserts the
encoding is correct end-to-end.  No SMTP server is required.

Covers:
  - :mod:`notify.providers._mime_utils` helper functions directly
  - :class:`~notify.providers.mail.ProviderEmail._render_` (async)
  - :class:`~notify.providers.smtp.smtp.SMTP._render_` (sync)
  - :class:`~notify.providers.ses.ses.Ses._render_` (async)
"""
from types import SimpleNamespace
from email.parser import BytesParser
from email.policy import default as policy_default
from pathlib import Path

import pytest

from notify.providers import _mime_utils as mu
from notify.providers.mail import ProviderEmail
from notify.providers.smtp.smtp import SMTP
from notify.providers.ses.ses import Ses


# ---------------------------------------------------------------- constants

NON_ASCII_SUBJECT = "Reservación confirmada ✈️"
NON_ASCII_BODY = "Hola José — su reservación está lista. 🌟"
NON_ASCII_HTML = "<p>Hola <b>José</b> — su reservación está lista. 🌟</p>"
NON_ASCII_SENDER = "Sr. Ñoño <s.nono@example.com>"
NON_ASCII_RCPT = "Señora Ümlaut <u.umlaut@example.com>"


# ---------------------------------------------------------------- fixtures

@pytest.fixture
def actor():
    """Lightweight Actor stand-in.

    ``_render_`` only reads ``to.account.address`` so a ``SimpleNamespace``
    is sufficient — no need to instantiate the full ``Actor`` model.
    """
    return SimpleNamespace(account=SimpleNamespace(address="u@example.com"))


@pytest.fixture
def non_ascii_attachment(tmp_path: Path):
    """Create a temporary PDF file with a non-ASCII filename."""
    f = tmp_path / "reporte_año.pdf"
    f.write_bytes(b"%PDF-1.4 fake")
    return f


# ---------------------------------------------------------------- helper-direct tests

def test_parse_actor_with_name():
    """``'Name <a@b.com>'`` splits into ``('Name', 'a@b.com')``."""
    name, addr = mu.parse_actor("Name <a@b.com>")
    assert name == "Name"
    assert addr == "a@b.com"


def test_parse_actor_bare_addr():
    """``'a@b.com'`` splits into ``('', 'a@b.com')`` — no display name."""
    name, addr = mu.parse_actor("a@b.com")
    assert name == ""
    assert addr == "a@b.com"


def test_build_message_envelope_subject_encoded():
    """Non-ASCII subject must appear as RFC 2047 encoded-word in raw bytes."""
    msg = mu.build_alternative_message(
        sender=NON_ASCII_SENDER,
        to="u@example.com",
        subject=NON_ASCII_SUBJECT,
    )
    raw = msg.as_bytes()
    # Subject must be RFC-2047 encoded, not raw UTF-8 bytes:
    assert b"Subject: =?utf-8?" in raw
    # Round-trip: decoded subject equals the original string.
    parsed = BytesParser(policy=policy_default).parsebytes(raw)
    assert parsed["Subject"] == NON_ASCII_SUBJECT


def test_build_message_envelope_from_encoded():
    """Non-ASCII From display name round-trips via RFC 2047."""
    msg = mu.build_alternative_message(
        sender=NON_ASCII_SENDER,
        to="u@example.com",
        subject="hi",
    )
    parsed = BytesParser(policy=policy_default).parsebytes(msg.as_bytes())
    from_str = str(parsed["From"])
    assert "Sr. Ñoño" in from_str
    assert "s.nono@example.com" in from_str


def test_build_message_envelope_subject_none():
    """``subject=None`` must not raise; the message serialises cleanly."""
    msg = mu.build_alternative_message(
        sender="a@b.com",
        to="u@example.com",
        subject=None,
    )
    assert msg.as_bytes()  # does not raise


def test_attach_text_part_charset():
    """Attached plain-text part must declare ``charset="utf-8"``."""
    msg = mu.build_alternative_message(sender="a@b", to="u@b", subject="x")
    mu.attach_text_part(msg, NON_ASCII_BODY, "plain")
    raw = msg.as_bytes()
    assert b'Content-Type: text/plain; charset="utf-8"' in raw


def test_attach_text_part_html_emoji_roundtrip():
    """HTML part containing emoji must round-trip without ``?`` substitution."""
    msg = mu.build_alternative_message(sender="a@b", to="u@b", subject="x")
    mu.attach_text_part(msg, NON_ASCII_HTML, "html")
    parsed = BytesParser(policy=policy_default).parsebytes(msg.as_bytes())
    body = parsed.get_body(preferencelist=("html",)).get_content()
    assert "José" in body
    assert "🌟" in body


def test_attach_file_rfc2231_filename(non_ascii_attachment: Path):
    """Non-ASCII attachment filename must be RFC 2231 percent-encoded."""
    msg = mu.build_alternative_message(sender="a@b", to="u@b", subject="x")
    mu.attach_file(msg, non_ascii_attachment)
    raw = msg.as_bytes()
    # RFC 2231 form: ``filename*=utf-8''<percent-encoded>``
    assert b"filename*=utf-8''" in raw
    # 'ñ' (U+00F1) encodes to %C3%B1 in percent-encoding:
    assert b"reporte_a%C3%B1o.pdf" in raw


def test_attach_file_auto_mimetype(tmp_path: Path):
    """A ``.pdf`` file without explicit ``mimetype`` detects ``application/pdf``."""
    f = tmp_path / "report.pdf"
    f.write_bytes(b"%PDF-1.4")
    msg = mu.build_alternative_message(sender="a@b", to="u@b", subject="x")
    mu.attach_file(msg, f)  # no explicit mimetype
    raw = msg.as_bytes()
    assert b"Content-Type: application/pdf" in raw


# ---------------------------------------------------------------- provider retrofit tests

@pytest.mark.asyncio
async def test_provider_email_render_uses_helper(actor):
    """``ProviderEmail._render_`` produces a UTF-8-safe message via the helper."""

    class _Stub(ProviderEmail):
        provider = "stub"

        async def _send_(self, *a, **kw):
            return None

    stub = _Stub()
    stub.actor = NON_ASCII_SENDER
    stub._template = None
    msg = await stub._render_(
        to=actor,
        message=NON_ASCII_BODY,
        subject=NON_ASCII_SUBJECT,
    )
    raw = msg.as_bytes()
    assert b"Subject: =?utf-8?" in raw
    assert b'charset="utf-8"' in raw


def test_provider_email_prepare_message_removed():
    """Resolved Q1 (spec §8): dead ``_prepare_message`` method must be gone."""
    assert not hasattr(ProviderEmail, "_prepare_message"), (
        "_prepare_message must be removed from ProviderEmail by TASK-002"
    )


def test_smtp_prepare_message_removed():
    """Symmetric deletion (new Q in spec §8): ``SMTP._prepare_message`` must be gone."""
    assert not hasattr(SMTP, "_prepare_message"), (
        "_prepare_message must be removed from SMTP by TASK-003"
    )


@pytest.mark.asyncio
async def test_smtp_render_uses_helper(actor):
    """Sync ``SMTP._render_`` produces a UTF-8-safe message.

    The test is async so that ``ProviderBase.__init__`` can find a running
    event loop (``SMTP`` extends ``ProviderBase`` which calls
    ``asyncio.get_running_loop()`` during construction). The ``_render_``
    method itself is sync and no ``await`` is needed for it.
    """
    smtp = SMTP(hostname="localhost", port=25, username="u", password="p")
    smtp.actor = NON_ASCII_SENDER
    smtp._template = None
    msg = smtp._render_(
        to=actor,
        message=NON_ASCII_BODY,
        subject=NON_ASCII_SUBJECT,
    )
    raw = msg.as_bytes()
    assert b"Subject: =?utf-8?" in raw
    assert b'charset="utf-8"' in raw


@pytest.mark.asyncio
async def test_ses_render_uses_helper(actor):
    """``Ses._render_`` (async, overridden) produces a UTF-8-safe message."""
    ses = Ses(
        aws_access_key_id="x",
        aws_secret_access_key="y",
        aws_region_name="us-east-1",
        sender_email=NON_ASCII_SENDER,
    )
    ses._template = None
    msg = await ses._render_(
        to=actor,
        message=NON_ASCII_BODY,
        subject=NON_ASCII_SUBJECT,
    )
    raw = msg.as_bytes()
    assert b"Subject: =?utf-8?" in raw
    assert b'charset="utf-8"' in raw


# ---------------------------------------------------------------- end-to-end integration

@pytest.mark.asyncio
async def test_end_to_end_non_ascii_serialization(actor, non_ascii_attachment: Path):
    """Full pipeline: build, attach text+html+file, serialise, reparse, verify."""

    class _Stub(ProviderEmail):
        provider = "stub"

        async def _send_(self, *a, **kw):
            return None

    stub = _Stub()
    stub.actor = NON_ASCII_SENDER
    stub._template = None

    msg = await stub._render_(
        to=actor,
        message=NON_ASCII_BODY,
        subject=NON_ASCII_SUBJECT,
    )
    stub.add_attachment(message=msg, filename=str(non_ascii_attachment))

    raw = msg.as_bytes()
    parsed = BytesParser(policy=policy_default).parsebytes(raw)

    # Subject round-trips correctly.
    assert parsed["Subject"] == NON_ASCII_SUBJECT

    # From display name preserved.
    assert "Sr. Ñoño" in str(parsed["From"])

    # Plain-text body decoded correctly.
    body_part = parsed.get_body(preferencelist=("plain",))
    assert body_part is not None
    body = body_part.get_content()
    assert "José" in body

    # Attachment filename round-trips.
    attachments = [
        p for p in parsed.walk()
        if p.get_content_disposition() == "attachment"
    ]
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "reporte_año.pdf"
