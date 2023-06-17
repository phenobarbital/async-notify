## for abstract email provider:
import os
import ssl
import asyncio
from abc import ABC
from typing import Union, Any
from collections.abc import Callable
from email import encoders
# from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.utils import formatdate
from functools import partial
import aiosmtplib
from notify.models import Actor
from notify.exceptions import ProviderError
# abstract class
from .base import ProviderBase, ProviderType


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

    def _prepare_message(
        self, to_address: Actor, message: Union[str, Any], content: Any
    ):  # pylint: disable=W0613
        """prepare_message."""
        if isinstance(content, dict):
            html = content["html"]
            text = content["text"]
        else:
            text = content
            html = None
        if html:
            message.add_header("Content-Type", "text/html")
            # message.add_header('Content-Type: multipart/mixed')
            # message.add_header('Content-Transfer-Encoding: base64')
            message.attach(MIMEText(html, "html"))
            # message.set_payload(html)
        else:
            message.add_header("Content-Type", "text/plain")
            message.attach(MIMEText(text, "plain"))
        return message

    async def _render_(
        self, to: Actor = None, message: str = None, subject: str = None, **kwargs
    ):
        """
        _render_.

        Returns the parseable version of Email.
        """
        # TODO: add attachments
        msg = MIMEMultipart("alternative")
        msg["From"] = self.actor
        if isinstance(to, list):
            # TODO: iterate over actors
            msg["To"] = ", ".join(to)
        else:
            msg["To"] = to.account.address
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)
        msg["sender"] = self.actor
        msg.preamble = subject
        if message:
            msg.attach(MIMEText(message, "plain"))
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
        msg.add_header("Content-Type", "text/html")
        msg.attach(MIMEText(content, "html"))
        return msg

    def add_attachment(self, message, filename, mimetype="octect-stream"):
        content = None
        with open(filename, "rb") as fp:
            content = fp.read()
        if mimetype in ("image/png"):
            part = MIMEImage(content)
        else:
            part = MIMEBase("application", "octect-stream")
            part.set_payload(content)
            encoders.encode_base64(part)
        file = os.path.basename(filename)
        part.add_header("Content-Disposition", "attachment", filename=str(file))
        message.attach(part)

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
        tasks = []
        for to in recipients:
            task = loop.create_task(
                self._send_(to, message, subject=subject, **kwargs)
            )
            fn = partial(self.__sent__, to, message, **kwargs)
            task.add_done_callback(fn)
            tasks.append(task)
            done, pending = await asyncio.wait(
                tasks,
                timeout=self.timeout,
                return_when="ALL_COMPLETED"
            )
            for task in done:
                exception = task.exception()
                if exception is not None:
                    self.logger.error(
                        f"Mail error: {exception}"
                    )
                else:
                    result = task.result()
                    results.append(result)
            for task in pending:
                self.logger.warning(
                    f"Task {task} pending, not completed"
                )
                task.cancel()
        return results
