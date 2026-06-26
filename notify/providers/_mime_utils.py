"""Private MIME-construction helpers shared by mail/smtp/ses providers.

This module is intentionally:
  - stdlib-only (no ``notify.*`` imports)
  - synchronous (callers await template rendering themselves)
  - private (leading underscore; not exported from ``__init__.py``)
"""
import os
import mimetypes
from email import encoders
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, parseaddr
from pathlib import Path
from typing import Optional, Union


def parse_actor(actor: str) -> tuple[str, str]:
    """Split an actor string into (display_name, address).

    Accepts either ``'Name <addr@host>'`` or ``'addr@host'``.
    Returns ``('', addr)`` when no display name is present.
    Centralises the parsing today scattered across mail.py / ses.py.

    Args:
        actor: A string in ``'Name <addr>'`` or ``'addr'`` form.

    Returns:
        A ``(display_name, address)`` tuple.  ``display_name`` is an
        empty string when no display name is present.
    """
    name, addr = parseaddr(actor or "")
    return name, addr


def format_address(actor: str) -> str:
    """Return an RFC-2047-encoded header value for From/To/Sender.

    Wraps :func:`email.utils.formataddr` with ``charset='utf-8'`` so
    non-ASCII display names are encoded as RFC 2047 encoded-words.
    Returns the empty string unchanged when *actor* is empty.

    Args:
        actor: A string in ``'Name <addr>'`` or ``'addr'`` form.

    Returns:
        An RFC-2047-safe header string suitable for From/To/Sender
        assignment.
    """
    if not actor:
        return ""
    name, addr = parse_actor(actor)
    return formataddr((name, addr), charset="utf-8")


def build_alternative_message(
    *,
    sender: str,
    to: Union[str, list[str]],
    subject: Optional[str],
    reply_to: Optional[str] = None,
) -> MIMEMultipart:
    """Construct a ``multipart/alternative`` envelope with UTF-8-safe headers.

    Uses the default ``compat32`` policy on the :class:`~email.mime.multipart.MIMEMultipart`
    object so that :class:`~email.header.Header` objects can be assigned
    to headers directly (the ``EmailPolicy`` / ``SMTPUTF8`` policy rejects
    ``Header`` objects via its header-factory).  The ``email.policy.SMTPUTF8``
    constant is preserved as a module-level reference so callers can attach
    it to transport-level negotiation if needed.

    Subject is encoded via :class:`email.header.Header` with ``charset='utf-8'``
    to produce RFC 2047 encoded-words (``=?utf-8?...?=``).  This encoding is
    ASCII-safe and survives relay through servers that do not advertise the
    ``SMTPUTF8`` extension (see spec §7 Known Risks #3).

    From/To/Reply-To headers are encoded via :func:`format_address`
    (:func:`email.utils.formataddr` with ``charset='utf-8'``).

    Args:
        sender: Envelope sender in ``'Name <addr>'`` or ``'addr'`` form.
        to: Recipient address(es).  A single string or a list of strings.
        subject: Email subject line.  ``None`` or empty string is
            accepted; produces an empty (but valid) Subject header.
        reply_to: Optional Reply-To address in the same form as *sender*.

    Returns:
        A :class:`email.mime.multipart.MIMEMultipart` instance with the
        envelope headers populated.  ``msg.policy`` is ``compat32``
        (the stdlib default) so that RFC 2047 header encoding via
        :class:`~email.header.Header` is applied correctly.
    """
    # Use the default compat32 policy so Header() objects work on assignment.
    # SMTPUTF8 / 8BITMIME negotiation at the transport level is handled by
    # aiosmtplib / smtplib automatically based on the message content.
    # RFC 2047 Subject encoding via Header() is ASCII-safe and survives
    # servers that do not advertise the SMTPUTF8 extension (spec §7 Risk #3).
    msg = MIMEMultipart("alternative")
    msg["From"] = format_address(sender)
    if isinstance(to, (list, tuple)):
        msg["To"] = ", ".join(format_address(addr) for addr in to)
    else:
        msg["To"] = format_address(to)
    # RFC 2047: Header(subject, 'utf-8') encodes non-ASCII chars as =?utf-8?..?=
    # so the Subject survives ASCII-only SMTP relays.
    msg["Subject"] = Header(subject or "", "utf-8")
    msg["Date"] = formatdate(localtime=True)
    if reply_to:
        msg["Reply-To"] = format_address(reply_to)
    return msg


def attach_text_part(
    msg: MIMEMultipart,
    body: str,
    subtype: str = "plain",
) -> None:
    """Attach a text part with an explicit UTF-8 charset declaration.

    Creates a :class:`email.mime.text.MIMEText` instance with
    ``_charset='utf-8'``, ensuring the ``Content-Type`` header contains
    ``charset="utf-8"`` and the payload is correctly encoded.

    Args:
        msg: The ``MIMEMultipart`` envelope to attach the part to.
        body: Plain-text or HTML string to attach.
        subtype: MIME subtype — ``'plain'`` (default) or ``'html'``.
    """
    msg.attach(MIMEText(body, subtype, _charset="utf-8"))


def attach_file(
    msg: MIMEMultipart,
    path: Union[str, "os.PathLike[str]"],
    mimetype: Optional[str] = None,
) -> None:
    """Attach a file with RFC 2231 filename encoding.

    Detects ``maintype/subtype`` via :func:`mimetypes.guess_type` when
    *mimetype* is ``None``.  Writes the ``Content-Disposition`` header
    using the ``(charset, language, value)`` tuple form so non-ASCII
    filenames round-trip correctly per RFC 2231.

    Args:
        msg: The ``MIMEMultipart`` envelope to attach the file to.
        path: Filesystem path to the file.  May be a :class:`str` or
            any :class:`os.PathLike`.
        mimetype: Explicit MIME type string, e.g. ``'application/pdf'``.
            When ``None`` the type is auto-detected from the file
            extension; falls back to ``'application/octet-stream'``.

    Raises:
        FileNotFoundError: If the file at *path* does not exist.
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
    # RFC 2231: filename=('charset', 'language', 'name') triggers percent-encoding
    part.add_header(
        "Content-Disposition",
        "attachment",
        filename=("utf-8", "", p.name),
    )
    msg.attach(part)
