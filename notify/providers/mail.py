## for abstract email provider:
import ssl
import asyncio
from abc import ABC
from typing import Union, Any
from collections.abc import Callable
import aiosmtplib
from notify.models import Actor
from notify.exceptions import ProviderError
# abstract class
from .base import ProviderBase, ProviderType
from notify.providers import _mime_utils as _mu


class ProviderEmail(ProviderBase, ABC):
    """
    ProviderEmail.

    Base class for All Email-based providers
    """

    provider_type = ProviderType.EMAIL
    blocking: str = 'asyncio'
    timeout: int = 60

    def __init__(self, *args, **kwargs):
        self.host: str = None
        self.port: int = None
        self._server: Callable = None
        super(ProviderEmail, self).__init__(*args, **kwargs)

    @property
    def user(self):
        return self.username

    async def close(self):
        if self._server:
            try:
                await self._server.quit()
            except aiosmtplib.errors.SMTPServerDisconnected:
                pass
            except Exception as err:  # pylint: disable=W0703
                self.logger.exception(err, stack_info=True)
            finally:
                self._server = None

    async def connect(self, *args, **kwargs):
        """
        Make a connection to the SMTP Server
        """
        context = ssl.SSLContext(ssl.PROTOCOL_TLS)
        context.options |= ssl.OP_NO_SSLv2
        context.options |= ssl.OP_NO_SSLv3
        context.options |= ssl.OP_NO_TLSv1
        context.options |= ssl.OP_NO_TLSv1_1
        context.options |= ssl.OP_NO_COMPRESSION
        try:
            self._server = aiosmtplib.SMTP(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                start_tls=True,
                tls_context=context,
                # loop=self._loop
            )
            try:
                await self._server.connect()
                self.logger.debug(
                    f":: {self.__name__}: Connected to: {self._server}"
                )
                try:
                    if self._server.is_ehlo_or_helo_needed:
                        await self._server.ehlo()
                except aiosmtplib.errors.SMTPHeloError as exc:
                    print(exc)
                await asyncio.sleep(.1)
                # # making authentication:
                # await self._server.login(
                #     username=self.username,
                #     password=self.password
                # )
            except aiosmtplib.errors.SMTPAuthenticationError as err:
                raise RuntimeError(
                    f"{self.__name__} Error: Invalid credentials: {err}"
                ) from err
            except aiosmtplib.errors.SMTPServerDisconnected as err:
                raise RuntimeError(
                    f"{self.__name__} Server Disconnected: {err}"
                ) from err
        except aiosmtplib.SMTPRecipientsRefused as err:
            raise RuntimeError(
                f"{self.__name__} Error: got SMTPRecipientsRefused: {err.recipients}"
            ) from err
        except (OSError, aiosmtplib.errors.SMTPException) as e:
            raise RuntimeError(f"{self.__name__} Error: got {e.__class__}, {e}") from e

    def is_connected(self):
        if self._server:
            return self._server.is_connected
        else:
            return False

    async def _render_(
        self, to: Actor = None, message: str = None, subject: str = None, **kwargs
    ):
        """Build a UTF-8-safe multipart/alternative message.

        Constructs the MIME envelope via :func:`_mime_utils.build_alternative_message`
        and attaches text/plain and text/html parts via
        :func:`_mime_utils.attach_text_part`.  Non-ASCII subjects, display
        names, and body text are encoded correctly per RFC 2047 / RFC 2231.

        Args:
            to: Recipient Actor (or list of addresses).
            message: Plain-text body content.
            subject: Email subject line.
            **kwargs: Additional template arguments forwarded to the Jinja2
                template renderer.

        Returns:
            A :class:`email.mime.multipart.MIMEMultipart` ready for transport.
        """
        recipient = (
            to.account.address if not isinstance(to, list)
            else ", ".join(to)
        )
        msg = _mu.build_alternative_message(
            sender=self.actor,
            to=recipient,
            subject=subject,
        )
        # mail.py historically sets a 'sender' header (smtp.py omits it —
        # intentional asymmetry per spec §7 Risk #1).
        msg["sender"] = _mu.format_address(self.actor)
        msg.preamble = subject or ""

        if message:
            _mu.attach_text_part(msg, message, "plain")

        if self._template:
            self._templateargs = {
                "recipient": to,
                "username": to,
                "message": message,
                "content": message,
                **kwargs,
            }
            content = await self._template.render_async(**self._templateargs)
        else:
            content = message
        _mu.attach_text_part(msg, content or "", "html")
        return msg

    def add_attachment(self, message, filename, mimetype="octect-stream"):
        """Attach a file to *message* with RFC 2231 filename encoding.

        The ``mimetype`` parameter is accepted for backwards-compatibility.
        The historically misspelled default ``"octect-stream"`` is treated as
        unknown and resolved via ``mimetypes.guess_type``; callers may pass
        a correctly-spelled explicit type to override detection.

        Args:
            message: The :class:`email.mime.multipart.MIMEMultipart` envelope.
            filename: Filesystem path to the file to attach.
            mimetype: Optional MIME type string.  The misspelled legacy
                default ``"octect-stream"`` is treated as absent.
        """
        # Treat the misspelled legacy default (and its correct spelling) as
        # "no explicit type" so mimetypes.guess_type can do its job.
        resolved = (
            None
            if mimetype in ("octect-stream", "application/octet-stream")
            else mimetype
        )
        _mu.attach_file(message, filename, resolved)

    async def _send_(
        self, to: Actor, message: str, subject: str, **kwargs
    ):  # pylint: disable=W0221
        """
        _send_.

        Logic associated with the construction of notifications
        """
        msg = await self._render_(to, message, subject, **kwargs)
        if "attachments" in kwargs:
            for attach in kwargs["attachments"]:
                self.add_attachment(message=msg, filename=attach)
        try:
            try:
                response = await self._server.send_message(msg)
                if self._debug is True:
                    self.logger.debug(response)
            except aiosmtplib.errors.SMTPServerDisconnected as err:
                raise RuntimeError(
                    f"{self.__name__} Server Disconnected {err}"
                ) from err
            return response
        except Exception as e:
            self.logger.exception(e)
            raise ProviderError(
                f"{self.__name__} Error: got {e.__class__}, {e}"
            ) from e

    async def send(
        self,
        recipient: list[Actor] = None,
        message: Union[str, Any] = None,
        subject: str = None,
        **kwargs,
    ):
        result = None
        # making the connection to the service:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.get_running_loop()
        asyncio.set_event_loop(loop)
        try:
            await self.connect()
        except Exception as err:
            raise ProviderError(
                f"Error connecting to Mail Backend: {err}"
            ) from err
        # after connection, proceed exactly like other connectors.
        ## recipients:
        # template (or message) for preparation
        message = await self._prepare_(
            recipient=recipient,
            message=message,
            **kwargs
        )
        results = []
        recipients = [recipient] if not isinstance(recipient, list) else recipient
        # tasks = []
        tasks = [self._send_(to, message, subject=subject, **kwargs) for to in recipients]

        for to, future in zip(recipients, asyncio.as_completed(tasks)):
            try:
                result = await future
                results.append(result)
            except Exception as e:
                self.logger.warning(
                    f'Task for recipient {to} raised exception: {e}'
                )
            try:
                await self.__sent__(to, message, result, loop=loop, **kwargs)
            except Exception as e:
                self.logger.exception(
                    f'Send for recipient {to} raised an exception: {e}',
                    stack_info=True
                )
        return results
