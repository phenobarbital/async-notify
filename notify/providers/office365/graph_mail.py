"""Microsoft Graph mail message construction (recipients, body, attachments).

This module turns render output and `send()` kwargs into typed `msgraph-sdk`
models: it loads attachments/inline images asynchronously, flattens `Actor`
recipients into Graph `Recipient` objects, and builds the `Message` sent to
Graph. Request execution (the `send_mail` / `draft_upload` strategy switch,
upload sessions, and Graph error mapping) lives alongside this in the same
module (see `GraphMailSender` / `map_odata_error`, added by TASK-24).
"""
import mimetypes
import re
from pathlib import Path
from typing import Iterable, Optional, Union

from msgraph.generated.models.body_type import BodyType
from msgraph.generated.models.email_address import EmailAddress
from msgraph.generated.models.file_attachment import FileAttachment
from msgraph.generated.models.importance import Importance
from msgraph.generated.models.item_body import ItemBody
from msgraph.generated.models.message import Message
from msgraph.generated.models.recipient import Recipient
from navconfig.logging import logging

from notify.exceptions import ProviderError
from notify.models import Actor, OutboundAttachment


logger = logging.getLogger(__name__)

#: Per-file hard limit (bytes). Larger files are rejected before any Graph call.
MAX_ATTACHMENT_SIZE: int = 150 * 1024 * 1024


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
        raise ValueError(
            f"Invalid importance: {value!r}; expected 'low', 'normal', or 'high'."
        ) from exc


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
