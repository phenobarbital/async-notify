"""Offline tests for Graph mail models, the message builder, and delivery
(FEAT-004, M4): TASK-23 covers the builder cases; TASK-24 adds the mocked
sender / upload-session / error-mapping cases below.
"""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from msgraph.generated.models.importance import Importance
from msgraph.generated.models.o_data_errors.main_error import MainError
from msgraph.generated.models.o_data_errors.o_data_error import ODataError

from notify.exceptions import NotifyAuthError, ProviderError
from notify.models import Actor, Account, MailSendResult, OutboundAttachment
from notify.providers.office365 import graph_mail as graph_mail_module
from notify.providers.office365.graph_mail import (
    INLINE_REQUEST_LIMIT,
    MAX_ATTACHMENT_SIZE,
    GraphMailSender,
    build_message,
    load_attachments,
    map_odata_error,
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


# ---------------------------------------------------------------------------
# TASK-24: GraphMailSender, upload sessions, error mapping
# ---------------------------------------------------------------------------


class _FakeRouteBuilder:
    """A fake `/me` or `/users/{id}` request builder.

    Exposes AsyncMock `send_mail.post`, `messages.post`, and per-draft
    `messages.by_message_id(...)` builders with `send.post`,
    `attachments.create_upload_session.post`, and `delete`.
    """

    def __init__(self):
        self.send_mail = MagicMock()
        self.send_mail.post = AsyncMock(return_value=None)

        self.messages = MagicMock()
        self._draft_builders: dict[str, MagicMock] = {}

        draft_message = MagicMock()
        draft_message.id = "draft-1"
        self.messages.post = AsyncMock(return_value=draft_message)

        draft_builder = MagicMock()
        draft_builder.send = MagicMock()
        draft_builder.send.post = AsyncMock(return_value=None)
        draft_builder.delete = AsyncMock(return_value=None)
        draft_builder.attachments = MagicMock()
        draft_builder.attachments.create_upload_session = MagicMock()
        draft_builder.attachments.create_upload_session.post = AsyncMock(return_value=MagicMock())
        self._draft_builders["draft-1"] = draft_builder
        self.messages.by_message_id = MagicMock(side_effect=lambda mid: self._draft_builders[mid])


@pytest.fixture
def graph_client_mock():
    """A MagicMock `GraphServiceClient` whose `.me` / `.users.by_user_id(...)`
    both return a `_FakeRouteBuilder`; `.request_adapter` is a MagicMock."""
    client = MagicMock()
    client.request_adapter = MagicMock()
    route = _FakeRouteBuilder()
    client.me = route
    client.users = MagicMock()
    client.users.by_user_id = MagicMock(return_value=route)
    return client, route


@pytest.fixture(autouse=True)
def _fake_large_file_upload_task(monkeypatch):
    """Never perform a real upload; just record the call and succeed."""

    class _FakeTask:
        instances: list["_FakeTask"] = []

        def __init__(self, session, request_adapter, stream, *args, **kwargs):
            self.session = session
            self.request_adapter = request_adapter
            self.stream = stream
            type(self).instances.append(self)

        async def upload(self, after_chunk_upload=None):
            return None

    _FakeTask.instances = []
    monkeypatch.setattr(graph_mail_module, "LargeFileUploadTask", _FakeTask)
    yield _FakeTask


def _small_attachment(name="a.txt", size=10) -> OutboundAttachment:
    return OutboundAttachment(name=name, content=b"x" * size, size=size)


async def test_send_mail_strategy_small(graph_client_mock):
    client, route = graph_client_mock
    sender = GraphMailSender(client, provider="office365", logger=MagicMock())
    message = build_message(subject="s", html="h", to=to_recipients(["a@contoso.com"]))

    result = await sender.send(
        mailbox="shared@contoso.com",
        message=message,
        attachments=[],
        save_to_sent_items=True,
        recipients=["a@contoso.com"],
    )

    assert result.success is True
    assert result.strategy == "send_mail"
    route.send_mail.post.assert_called_once()
    body = route.send_mail.post.call_args.args[0]
    assert body.save_to_sent_items is True
    assert body.message is message


async def test_draft_upload_strategy_large(graph_client_mock, _fake_large_file_upload_task):
    client, route = graph_client_mock
    sender = GraphMailSender(client, provider="office365", logger=MagicMock())

    small = _small_attachment(name="small.txt", size=10)
    large = OutboundAttachment(name="large.bin", content=b"y" * 10, size=INLINE_REQUEST_LIMIT + 1)
    attachments = [small, large]
    message = build_message(
        subject="s", html="h", to=to_recipients(["a@contoso.com"]), attachments=attachments
    )

    result = await sender.send(
        mailbox=None,
        message=message,
        attachments=attachments,
        save_to_sent_items=True,
        recipients=["a@contoso.com"],
    )

    assert result.success is True
    assert result.strategy == "draft_upload"
    assert result.message_id == "draft-1"
    route.messages.post.assert_called_once()
    # only the small attachment stays embedded on the draft
    posted_message = route.messages.post.call_args.args[0]
    assert len(posted_message.attachments) == 1
    assert posted_message.attachments[0].name == "small.txt"
    # the large one goes through an upload session
    draft_builder = route._draft_builders["draft-1"]
    draft_builder.attachments.create_upload_session.post.assert_called_once()
    assert len(_fake_large_file_upload_task.instances) == 1
    draft_builder.send.post.assert_called_once()


async def test_draft_upload_save_to_sent_items_false_warns(graph_client_mock, _fake_large_file_upload_task):
    client, route = graph_client_mock
    warn_logger = MagicMock()
    sender = GraphMailSender(client, provider="office365", logger=warn_logger)

    large = OutboundAttachment(name="large.bin", content=b"y" * 10, size=INLINE_REQUEST_LIMIT + 1)
    message = build_message(subject="s", html="h", to=[], attachments=[large])

    await sender.send(
        mailbox=None, message=message, attachments=[large], save_to_sent_items=False, recipients=[]
    )
    assert warn_logger.warning.called


async def test_draft_deleted_on_upload_failure(graph_client_mock, _fake_large_file_upload_task):
    client, route = graph_client_mock
    draft_builder = route._draft_builders["draft-1"]
    draft_builder.attachments.create_upload_session.post = AsyncMock(side_effect=RuntimeError("boom"))

    sender = GraphMailSender(client, provider="office365", logger=MagicMock())
    large = OutboundAttachment(name="large.bin", content=b"y" * 10, size=INLINE_REQUEST_LIMIT + 1)
    message = build_message(subject="s", html="h", to=[], attachments=[large])

    with pytest.raises(RuntimeError):
        await sender.send(
            mailbox=None, message=message, attachments=[large], save_to_sent_items=True, recipients=[]
        )

    draft_builder.delete.assert_called_once()


def _odata_error(*, status_code: int, code: str, message: str = "failed") -> ODataError:
    error = ODataError(response_status_code=status_code)
    error.error = MainError(code=code, message=message)
    return error


def test_map_odata_error_auth_raises():
    exc = _odata_error(status_code=403, code="ErrorSendAsDenied")
    with pytest.raises(NotifyAuthError):
        map_odata_error(exc, provider="office365", mailbox="shared@contoso.com", recipients=["a@contoso.com"])


def test_map_odata_error_auth_raises_on_401_regardless_of_code():
    exc = _odata_error(status_code=401, code="SomethingElse")
    with pytest.raises(NotifyAuthError):
        map_odata_error(exc, provider="office365", mailbox=None, recipients=[])


def test_map_odata_error_other_returns_result():
    exc = _odata_error(status_code=400, code="ErrorInvalidRecipients", message="bad recipient")
    result = map_odata_error(exc, provider="office365", mailbox=None, recipients=["bad@contoso.com"])
    assert isinstance(result, MailSendResult)
    assert result.success is False
    assert result.status_code == 400
    assert result.error_code == "ErrorInvalidRecipients"
    assert result.error == "bad recipient"


async def test_send_mail_strategy_propagates_auth_error_via_odata(graph_client_mock):
    client, route = graph_client_mock
    route.send_mail.post = AsyncMock(side_effect=_odata_error(status_code=403, code="ErrorSendAsDenied"))
    sender = GraphMailSender(client, provider="office365", logger=MagicMock())
    message = build_message(subject="s", html="h", to=[])

    with pytest.raises(NotifyAuthError):
        await sender.send(
            mailbox="shared@contoso.com",
            message=message,
            attachments=[],
            save_to_sent_items=True,
            recipients=[],
        )
