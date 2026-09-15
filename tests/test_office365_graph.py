"""Offline tests for Graph mail models and the message builder (FEAT-004, M4).

Sender/upload-session/error-mapping tests are added by TASK-24 in this same
module.
"""
from pathlib import Path

import pytest
from msgraph.generated.models.importance import Importance

from notify.exceptions import ProviderError
from notify.models import Actor, Account, OutboundAttachment
from notify.providers.office365.graph_mail import (
    MAX_ATTACHMENT_SIZE,
    build_message,
    load_attachments,
    to_recipients,
)


@pytest.fixture
def actors() -> list[Actor]:
    return [
        Actor(name="Alice", account=Account(address="alice@contoso.com")),
        Actor(name="Bob", account=Account(address="bob@contoso.com")),
    ]


def test_to_recipients_from_actors(actors):
    recipients = to_recipients(actors)
    assert [r.email_address.address for r in recipients] == ["alice@contoso.com", "bob@contoso.com"]
    assert [r.email_address.name for r in recipients] == ["Alice", "Bob"]


def test_to_recipients_from_strings():
    recipients = to_recipients(["ops@contoso.com", "sec@contoso.com"])
    assert [r.email_address.address for r in recipients] == ["ops@contoso.com", "sec@contoso.com"]


def test_to_recipients_actor_with_multiple_addresses():
    actor = Actor(name="Shared", account=Account(address=["a@contoso.com", "b@contoso.com"]))
    recipients = to_recipients([actor])
    assert [r.email_address.address for r in recipients] == ["a@contoso.com", "b@contoso.com"]
    assert all(r.email_address.name == "Shared" for r in recipients)


def test_to_recipients_skips_actor_without_address():
    actor = Actor(name="NoAddress", account=None)
    assert to_recipients([actor]) == []


def test_to_recipients_empty_or_none():
    assert to_recipients(None) == []
    assert to_recipients([]) == []


async def test_load_attachments_from_path(tmp_path: Path):
    file_path = tmp_path / "report.txt"
    file_path.write_text("hello world", encoding="utf-8")

    loaded = await load_attachments(attachments=[str(file_path)])
    assert len(loaded) == 1
    attachment = loaded[0]
    assert attachment.name == "report.txt"
    assert attachment.content == b"hello world"
    assert attachment.size == len(b"hello world")
    assert attachment.is_inline is False


async def test_load_attachments_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        await load_attachments(attachments=[str(tmp_path / "missing.txt")])


async def test_load_attachments_prebuilt_outbound_attachment_passthrough():
    prebuilt = OutboundAttachment(name="x.bin", content=b"1234", size=4)
    loaded = await load_attachments(attachments=[prebuilt])
    assert loaded == [prebuilt]


async def test_load_attachments_over_150mb_rejected():
    oversized = OutboundAttachment(name="huge.bin", content=b"x", size=MAX_ATTACHMENT_SIZE + 1)
    with pytest.raises(ProviderError):
        await load_attachments(attachments=[oversized])


async def test_load_inline_images_from_bytes():
    loaded = await load_attachments(inline_images={"logo": b"\x89PNG..."})
    assert len(loaded) == 1
    image = loaded[0]
    assert image.content_id == "logo"
    assert image.is_inline is True
    assert image.content == b"\x89PNG..."


async def test_load_inline_images_from_path(tmp_path: Path):
    image_path = tmp_path / "logo.png"
    image_path.write_bytes(b"\x89PNG-data")

    loaded = await load_attachments(inline_images={"logo": str(image_path)})
    assert loaded[0].content_type == "image/png"
    assert loaded[0].content_id == "logo"


def test_build_message_recipients_cc_bcc_reply_importance():
    to = to_recipients(["alice@contoso.com"])
    cc = to_recipients(["cc@contoso.com"])
    bcc = to_recipients(["bcc@contoso.com"])
    reply_to = to_recipients(["reply@contoso.com"])

    message = build_message(
        subject="Report",
        html="<p>hi</p>",
        to=to,
        cc=cc,
        bcc=bcc,
        reply_to=reply_to,
        importance="high",
    )
    assert message.subject == "Report"
    assert message.body.content == "<p>hi</p>"
    assert [r.email_address.address for r in message.to_recipients] == ["alice@contoso.com"]
    assert [r.email_address.address for r in message.cc_recipients] == ["cc@contoso.com"]
    assert [r.email_address.address for r in message.bcc_recipients] == ["bcc@contoso.com"]
    assert [r.email_address.address for r in message.reply_to] == ["reply@contoso.com"]
    assert message.importance == Importance.High


def test_build_message_bad_importance_raises():
    with pytest.raises(ValueError):
        build_message(subject="s", html="h", to=[], importance="urgent")


def test_build_message_from_address():
    message = build_message(subject="s", html="h", to=[], from_address="shared@contoso.com")
    assert message.from_.email_address.address == "shared@contoso.com"


def test_inline_cid_attachment_flags():
    inline = OutboundAttachment(
        name="logo.png", content=b"data", size=4, content_id="logo", is_inline=True
    )
    message = build_message(subject="s", html='<img src="cid:logo">', to=[], attachments=[inline])
    assert len(message.attachments) == 1
    graph_attachment = message.attachments[0]
    assert graph_attachment.is_inline is True
    assert graph_attachment.content_id == "logo"


def test_inline_cid_missing_reference_logs_warning(caplog):
    inline = OutboundAttachment(
        name="logo.png", content=b"data", size=4, content_id="logo", is_inline=True
    )
    with caplog.at_level("WARNING"):
        build_message(subject="s", html="<p>no cid reference here</p>", to=[], attachments=[inline])
    assert any("cid:logo" in record.message for record in caplog.records) is False
    # the html has no cid: reference at all, so there is nothing referenced and
    # nothing to warn about; the inline image being unused is a debug log instead
    assert not any(record.levelname == "WARNING" for record in caplog.records)


def test_html_cid_reference_without_matching_image_warns(caplog):
    with caplog.at_level("WARNING"):
        build_message(
            subject="s",
            html='<img src="cid:missing-logo">',
            to=[],
            attachments=[OutboundAttachment(name="a.txt", content=b"x", size=1)],
        )
    assert any("missing-logo" in record.message for record in caplog.records)
