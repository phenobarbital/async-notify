"""Microsoft Graph mail message construction, delivery, and error mapping.

This module turns render output and `send()` kwargs into typed `msgraph-sdk`
models (attachment/inline-image loading, `Actor` → `Recipient` flattening,
`build_message`), then executes the send: one direct `sendMail` call for
small requests, or a draft → upload-session → send workflow for large
attachments (`GraphMailSender`), mapping Graph `ODataError`s to either a
raised `NotifyAuthError` or a failed `MailSendResult` (`map_odata_error`).
"""

import mimetypes
import re
from collections.abc import Iterable
from io import BytesIO
from pathlib import Path
from typing import Any, Optional, Union

from msgraph import GraphServiceClient
from msgraph.generated.models.attachment_item import AttachmentItem
from msgraph.generated.models.attachment_type import AttachmentType
from msgraph.generated.models.body_type import BodyType
from msgraph.generated.models.email_address import EmailAddress
from msgraph.generated.models.file_attachment import FileAttachment
from msgraph.generated.models.importance import Importance
from msgraph.generated.models.item_body import ItemBody
from msgraph.generated.models.message import Message
from msgraph.generated.models.o_data_errors.o_data_error import ODataError
from msgraph.generated.models.recipient import Recipient
from msgraph.generated.users.item.messages.item.attachments.create_upload_session.create_upload_session_post_request_body import (  # noqa: E501
    CreateUploadSessionPostRequestBody,
)
from msgraph.generated.users.item.send_mail.send_mail_post_request_body import SendMailPostRequestBody
from msgraph_core.tasks.large_file_upload import LargeFileUploadTask
from navconfig.logging import logging

from notify.exceptions import NotifyAuthError, ProviderError
from notify.models import Actor, MailSendResult, OutboundAttachment

logger = logging.getLogger(__name__)

#: Aggregate raw size (bytes) of all attachments (inline images included)
#: that still fits in one `sendMail` request. Above this, the `draft_upload`
#: strategy is used instead.
INLINE_REQUEST_LIMIT: int = 3 * 1024 * 1024

#: Per-file hard limit (bytes). Larger files are rejected before any Graph call.
MAX_ATTACHMENT_SIZE: int = 150 * 1024 * 1024

#: Upload-session chunk size for large mail attachments. Graph's mail
#: attachment upload sessions require each PUT fragment to be a multiple of
#: 320 KiB and strictly under 4 MiB; `msgraph_core.LargeFileUploadTask`'s own
#: default (5,242,880 bytes = 5 MiB) exceeds that and is rejected by Graph on
#: the very first chunk, so it must never be used here.
UPLOAD_CHUNK_SIZE: int = 320 * 1024 * 12  # 3,932,160 bytes (~3.75 MiB)

#: Graph `error.code` values that mean "auth/permission failure" and must
#: raise `NotifyAuthError` instead of returning a failed `MailSendResult`.
AUTH_ERROR_CODES: frozenset[str] = frozenset(
    {
        "ErrorSendAsDenied",
        "ErrorAccessDenied",
        "AccessDenied",
        "InvalidAuthenticationToken",
        "Authorization_RequestDenied",
        "MailboxNotEnabledForRESTAPI",
    }
)


async def _read_file(path: Path) -> bytes:
    """Read a file's bytes asynchronously (never blocks the event loop)."""
    import aiofiles

    async with aiofiles.open(path, mode="rb") as fh:
        return await fh.read()


def _check_size(name: str, size: int) -> None:
    """Raise `ProviderError` if `size` exceeds `MAX_ATTACHMENT_SIZE`."""
    if size > MAX_ATTACHMENT_SIZE:
        raise ProviderError(
            f"Attachment {name!r} is {size} bytes, exceeding the {MAX_ATTACHMENT_SIZE}-byte per-file limit."
        )


async def _load_regular(item: Union[str, Path, OutboundAttachment]) -> OutboundAttachment:
    """Load one regular (non-inline) attachment.

    Raises:
        FileNotFoundError: If `item` is a path that does not exist.
        ProviderError: If the file exceeds `MAX_ATTACHMENT_SIZE`.
    """
    if isinstance(item, OutboundAttachment):
        _check_size(item.name, item.size)
        return item
    path = Path(item)
    if not path.exists():
        raise FileNotFoundError(f"Attachment not found: {path}")
    content = await _read_file(path)
    _check_size(path.name, len(content))
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return OutboundAttachment(name=path.name, content=content, content_type=content_type, size=len(content))


async def _load_inline(content_id: str, source: Union[str, Path, bytes]) -> OutboundAttachment:
    """Load one inline CID image.

    Raises:
        FileNotFoundError: If `source` is a path that does not exist.
        ProviderError: If the image exceeds `MAX_ATTACHMENT_SIZE`.
    """
    if isinstance(source, (bytes, bytearray)):
        content = bytes(source)
        name = content_id
        content_type = "application/octet-stream"
    else:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Inline image not found: {path}")
        content = await _read_file(path)
        name = path.name
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    _check_size(name, len(content))
    return OutboundAttachment(
        name=name,
        content=content,
        content_type=content_type,
        size=len(content),
        content_id=content_id,
        is_inline=True,
    )


async def load_attachments(
    attachments: Optional[list[Union[str, Path, OutboundAttachment]]] = None,
    inline_images: Optional[dict[str, Union[str, Path, bytes]]] = None,
) -> list[OutboundAttachment]:
    """Read files asynchronously into `OutboundAttachment` models.

    Args:
        attachments: Regular attachments — file paths or pre-built
            `OutboundAttachment` instances.
        inline_images: A mapping of CID key to file path or raw bytes; each
            becomes an `OutboundAttachment` with `content_id=key`,
            `is_inline=True`.

    Returns:
        list[OutboundAttachment]: Inline images first, then regular
        attachments, in the order given.

    Raises:
        FileNotFoundError: For a missing path.
        ProviderError: For a file above `MAX_ATTACHMENT_SIZE`.
    """
    loaded: list[OutboundAttachment] = []
    for content_id, source in (inline_images or {}).items():
        loaded.append(await _load_inline(content_id, source))
    for item in attachments or []:
        loaded.append(await _load_regular(item))
    return loaded


def to_recipients(addresses: Optional[Iterable[Union[str, Actor]]]) -> list[Recipient]:
    """Flatten `Actor`/`str` addresses into Graph `Recipient` objects.

    Args:
        addresses: `Actor` instances (using `account.address`, which may be a
            single address or a list of addresses) or plain address strings.

    Returns:
        list[Recipient]: One `Recipient` per resolved address. An `Actor`
        whose `account.address` is a list contributes one `Recipient` per
        address in that list.
    """
    recipients: list[Recipient] = []
    for item in addresses or []:
        if isinstance(item, Actor):
            account = item.account
            address = account.address if account else None
            if not address:
                logger.warning("Actor %r has no account.address; skipped as a recipient.", item.name)
                continue
            address_list = address if isinstance(address, list) else [address]
            for one in address_list:
                recipients.append(Recipient(email_address=EmailAddress(address=one, name=item.name)))
        else:
            recipients.append(Recipient(email_address=EmailAddress(address=str(item))))
    return recipients


def _to_importance(value: str) -> Importance:
    """Map a `low`/`normal`/`high` string to `msgraph`'s `Importance` enum.

    Raises:
        ValueError: For any other value.
    """
    try:
        return Importance(str(value).lower())
    except ValueError as exc:
        raise ValueError(f"Invalid importance: {value!r}; expected 'low', 'normal', or 'high'.") from exc


_CID_REFERENCE_RE = re.compile(r"cid:([\w.\-@]+)", re.IGNORECASE)


def _check_cid_references(html: str, attachments: list[OutboundAttachment]) -> None:
    """Cross-check `cid:<key>` references in `html` against inline attachments.

    A `cid:<key>` with no matching inline image logs a warning. An inline
    image the HTML never references is still attached, with a debug log.
    """
    inline_ids = {a.content_id for a in attachments if a.is_inline and a.content_id}
    referenced = set(_CID_REFERENCE_RE.findall(html or ""))
    for missing in sorted(referenced - inline_ids):
        logger.warning("HTML references cid:%s with no matching inline image.", missing)
    for unused in sorted(inline_ids - referenced):
        logger.debug("Inline image %s is attached but not referenced by cid: in the HTML body.", unused)


def _to_file_attachment(attachment: OutboundAttachment) -> FileAttachment:
    """Build a Graph `FileAttachment` (odata type `#microsoft.graph.fileAttachment`) from one `OutboundAttachment`."""
    return FileAttachment(
        name=attachment.name,
        content_type=attachment.content_type,
        content_bytes=attachment.content,
        content_id=attachment.content_id,
        is_inline=attachment.is_inline,
    )


def build_message(
    *,
    subject: Optional[str],
    html: str,
    to: list[Recipient],
    cc: Optional[list[Recipient]] = None,
    bcc: Optional[list[Recipient]] = None,
    reply_to: Optional[list[Recipient]] = None,
    importance: Optional[str] = None,
    from_address: Optional[str] = None,
    attachments: Optional[list[OutboundAttachment]] = None,
) -> Message:
    """Build the Graph `Message` for one `send()` call.

    Args:
        subject: The message subject.
        html: The rendered HTML body (`Body` is always `BodyType.Html`).
        to: `To` recipients.
        cc: `Cc` recipients.
        bcc: `Bcc` recipients.
        reply_to: `ReplyTo` recipients.
        importance: `low` | `normal` | `high`; anything else raises `ValueError`.
        from_address: When given, sets `Message.from_` to this address.
        attachments: Attachments to embed as `FileAttachment` objects.

    Returns:
        Message: Ready to be sent via `send_mail.post` or a draft `messages.post`.

    Raises:
        ValueError: If `importance` is set to an unrecognised value.
    """
    message = Message(subject=subject, body=ItemBody(content_type=BodyType.Html, content=html), to_recipients=to)
    if cc:
        message.cc_recipients = cc
    if bcc:
        message.bcc_recipients = bcc
    if reply_to:
        message.reply_to = reply_to
    if importance is not None:
        message.importance = _to_importance(importance)
    if from_address:
        message.from_ = Recipient(email_address=EmailAddress(address=from_address))
    if attachments:
        _check_cid_references(html, attachments)
        message.attachments = [_to_file_attachment(a) for a in attachments]
    return message


def map_odata_error(exc: ODataError, *, provider: str, mailbox: Optional[str], recipients: list[str]) -> MailSendResult:
    """Map a Graph `ODataError` to a failed `MailSendResult`, or raise for auth/permission failures.

    Args:
        exc: The `ODataError` raised by an `msgraph-sdk` request.
        provider: The provider name to stamp on the result (e.g. `"office365"`).
        mailbox: The mailbox the send was attempted against, or `None` for `/me`.
        recipients: The addresses the send was attempted for.

    Returns:
        MailSendResult: A `success=False` result for any non-auth Graph failure
        (e.g. `ErrorInvalidRecipients` / 400).

    Raises:
        NotifyAuthError: When `response_status_code` is 401/403, or
            `error.code` is one of `AUTH_ERROR_CODES` — never leaks Graph
            response internals beyond `code`/`message`/`status_code`.
    """
    error = exc.error
    code = getattr(error, "code", None) if error else None
    message = (getattr(error, "message", None) if error else None) or exc.message or str(exc)
    status_code = exc.response_status_code

    if status_code in (401, 403) or code in AUTH_ERROR_CODES:
        raise NotifyAuthError(f"O365 Graph mail send denied (code={code}, status={status_code}): {message}")

    return MailSendResult(
        success=False,
        provider=provider,
        mailbox=mailbox,
        recipients=recipients,
        status_code=status_code,
        error_code=code,
        error=message,
    )


class GraphMailSender:
    """Execute a Graph mail send using the `send_mail` or `draft_upload` strategy."""

    def __init__(self, graph: GraphServiceClient, *, provider: str, logger: logging.Logger) -> None:
        """Build a sender bound to one `GraphServiceClient`.

        Args:
            graph: The Graph client to issue requests through.
            provider: The provider name stamped on every `MailSendResult`.
            logger: The provider's own logger (never a module-level logger),
                so `save_to_sent_items` warnings surface under the caller's name.
        """
        self._graph = graph
        self._provider = provider
        self._logger = logger

    def _route(self, mailbox: Optional[str]):
        """Return the Graph request builder for `mailbox` (`/users/{mailbox}`) or `/me`."""
        if mailbox:
            return self._graph.users.by_user_id(mailbox)
        return self._graph.me

    def _select_embedded_indices(self, attachments: list[OutboundAttachment]) -> list[int]:
        """Pick which attachment indices stay embedded on the draft (inline images first)."""
        order = sorted(range(len(attachments)), key=lambda i: (not attachments[i].is_inline, i))
        selected: list[int] = []
        total = 0
        for i in order:
            size = attachments[i].size
            if total + size <= INLINE_REQUEST_LIMIT:
                selected.append(i)
                total += size
        return sorted(selected)

    async def _upload_large_attachment(self, draft_route: Any, attachment: OutboundAttachment) -> None:
        """Upload one large attachment onto an existing draft via an upload session.

        Preserves `content_id`/`is_inline` so an inline CID image that
        overflows the embed budget still renders instead of silently
        becoming a regular attachment.
        """
        upload_body = CreateUploadSessionPostRequestBody(
            attachment_item=AttachmentItem(
                attachment_type=AttachmentType.File,
                name=attachment.name,
                size=attachment.size,
                content_type=attachment.content_type,
                content_id=attachment.content_id,
                is_inline=attachment.is_inline,
            )
        )
        session = await draft_route.attachments.create_upload_session.post(upload_body)
        task = LargeFileUploadTask(
            session,
            self._graph.request_adapter,
            BytesIO(attachment.content),
            max_chunk_size=UPLOAD_CHUNK_SIZE,
        )
        await task.upload()

    async def _send_mail_strategy(
        self,
        route: Any,
        message: Message,
        save_to_sent_items: bool,
        mailbox: Optional[str],
        recipients: list[str],
    ) -> MailSendResult:
        """Send everything in one `sendMail` call (total size within `INLINE_REQUEST_LIMIT`)."""
        body = SendMailPostRequestBody(message=message, save_to_sent_items=save_to_sent_items)
        await route.send_mail.post(body)
        return MailSendResult(
            success=True, provider=self._provider, mailbox=mailbox, recipients=recipients, strategy="send_mail"
        )

    async def _draft_upload_strategy(
        self,
        route: Any,
        message: Message,
        attachments: list[OutboundAttachment],
        save_to_sent_items: bool,
        mailbox: Optional[str],
        recipients: list[str],
    ) -> MailSendResult:
        """Create a draft, upload the remaining large files, then send the draft.

        A sent draft always lands in Sent Items — `save_to_sent_items=False`
        only logs a warning. If the upload or the final send fails, the draft
        is deleted best-effort before the failure propagates.
        """
        if save_to_sent_items is False:
            self._logger.warning(
                "O365 draft_upload strategy always saves to Sent Items; save_to_sent_items=False is ignored."
            )

        embedded_indices = self._select_embedded_indices(attachments)
        if message.attachments:
            message.attachments = [message.attachments[i] for i in embedded_indices]

        draft = await route.messages.post(message)
        draft_id = getattr(draft, "id", None)
        if not draft_id:
            raise ProviderError("Graph did not return a draft message id for the upload-session strategy.")
        draft_route = route.messages.by_message_id(draft_id)

        embedded_set = set(embedded_indices)
        large_indices = [i for i in range(len(attachments)) if i not in embedded_set]

        try:
            for i in large_indices:
                await self._upload_large_attachment(draft_route, attachments[i])
            await draft_route.send.post()
        except Exception:
            try:
                await draft_route.delete()
            except Exception:  # noqa: BLE001 - best-effort cleanup, never masks the real error
                self._logger.debug("Best-effort deletion of failed O365 draft %s also failed.", draft_id)
            raise

        return MailSendResult(
            success=True,
            provider=self._provider,
            mailbox=mailbox,
            recipients=recipients,
            strategy="draft_upload",
            message_id=draft_id,
        )

    async def send(
        self,
        *,
        mailbox: Optional[str],
        message: Message,
        attachments: list[OutboundAttachment],
        save_to_sent_items: bool,
        recipients: list[str],
    ) -> MailSendResult:
        """Choose the strategy by total attachment size, send, and return a `MailSendResult`.

        Args:
            mailbox: `None` routes through `/me`; otherwise `/users/{mailbox}`.
            message: The Graph `Message` built by `build_message` (already
                carries every attachment as a `FileAttachment`).
            attachments: The same attachments as `OutboundAttachment` models,
                used to compute the total size and to drive uploads.
            save_to_sent_items: Whether the send should land in Sent Items
                (`send_mail` strategy only; `draft_upload` always does).
            recipients: The resolved recipient addresses, for the result.

        Returns:
            MailSendResult: `success=True` on delivery, or `success=False` for
            a non-auth Graph failure.

        Raises:
            NotifyAuthError: Via `map_odata_error`, for auth/permission failures.
        """
        total_size = sum(a.size for a in attachments)
        route = self._route(mailbox)
        try:
            if total_size <= INLINE_REQUEST_LIMIT:
                return await self._send_mail_strategy(route, message, save_to_sent_items, mailbox, recipients)
            return await self._draft_upload_strategy(
                route, message, attachments, save_to_sent_items, mailbox, recipients
            )
        except ODataError as exc:
            return map_odata_error(exc, provider=self._provider, mailbox=mailbox, recipients=recipients)
