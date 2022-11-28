## for abstract email provider:
import os
import ssl
import asyncio
from abc import ABC
from typing import (
    Union,
    Any
)
from collections.abc import Callable
from email import encoders
# from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.utils import formatdate
import aiosmtplib
from notify.models import Actor
from notify.exceptions import ProviderError
# abstract class
from .abstract import ProviderBase, ProviderType


class ProviderEmail(ProviderBase, ABC):
    """
    ProviderEmail.

    Base class for All Email-based providers
    """

    provider_type = ProviderType.EMAIL

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
            except Exception as err: # pylint: disable=W0703
                self._logger.exception(err, stack_info=True)
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
                self._logger.debug(f':: {self.__name__}: Connected to: {self._server}')
                try:
                    if self._server.is_ehlo_or_helo_needed:
                        await self._server.ehlo()
                except aiosmtplib.errors.SMTPHeloError:
                    pass
                await asyncio.sleep(0)
                # # making authentication:
                # await self._server.login(
                #     username=self.username,
                #     password=self.password
                # )
            except aiosmtplib.errors.SMTPAuthenticationError as err:
                raise RuntimeError(
                    f'{self.__name__} Error: Invalid credentials: {err}'
                ) from err
            except aiosmtplib.errors.SMTPServerDisconnected as err:
                raise RuntimeError(
                    f'{self.__name__} Server Disconnected: {err}'
                ) from err
        except aiosmtplib.SMTPRecipientsRefused as err:
            raise RuntimeError(
                f'{self.__name__} Error: got SMTPRecipientsRefused: {err.recipients}'
            ) from err
        except (OSError, aiosmtplib.errors.SMTPException) as e:
            raise RuntimeError(
                f'{self.__name__} Error: got {e.__class__}, {e}'
            ) from e

    def is_connected(self):
        if self._server:
            return self._server.is_connected
        else:
            return False

    def _prepare_message(self, to_address: Actor, message: Union[str, Any], content: Any): # pylint: disable=W0613
        """prepare_message.
        """
        if isinstance(content, dict):
            html = content['html']
            text = content['text']
        else:
            text = content
            html = None
        if html:
            message.add_header('Content-Type', 'text/html')
            #message.add_header('Content-Type: multipart/mixed')
            #message.add_header('Content-Transfer-Encoding: base64')
            message.attach(MIMEText(html, 'html'))
            #message.set_payload(html)
        else:
            message.add_header('Content-Type', 'text/plain')
            message.attach(MIMEText(text, 'plain'))
        return message

    async def _render_(
            self,
            to: Actor = None,
            subject: str = None,
            content: str = None,
            **kwargs
        ):
        """
        _render.

        Returns the parseable version of Email.
        """
        #TODO: add attachments
        message = MIMEMultipart('alternative')
        message['From'] = self.actor
        if isinstance(to, list):
            # TODO: iterate over actors
            message['To'] = ", ".join(to)
        else:
            message['To'] = to.account.address
        message['Subject'] = subject
        message['Date'] = formatdate(localtime=True)
        message['sender'] = self.actor
        message.preamble = subject
        if content:
            message.attach(MIMEText(content, 'plain'))
        if self._template:
            self._templateargs = {
                "recipient": to,
                "username": to,
                "message": content,
                "content": content,
                **kwargs
            }
            msg = self._template.render(**self._templateargs)
        else:
            msg = content
        message.add_header('Content-Type', 'text/html')
        #message.add_header('Content-Type', 'multipart/mixed')
        #message.add_header('Content-Transfer-Encoding', 'base64')
        message.attach(MIMEText(msg, 'html'))
        #message.set_payload(msg)
        return message

    def add_attachment(self, message, filename, mimetype='octect-stream'):
        content = None
        with open(filename, 'rb') as fp:
            content = fp.read()
        if mimetype in ('image/png'):
            part = MIMEImage(content)
        else:
            part = MIMEBase('application', 'octect-stream')
            part.set_payload(content)
            encoders.encode_base64(part)
        file = os.path.basename(filename)
        part.add_header(
            'Content-Disposition', 'attachment', filename=str(file)
        )
        message.attach(part)

    async def _send_(self, to: Actor, message: str, subject: str, **kwargs): # pylint: disable=W0221
        """
        _send.

        Logic associated with the construction of notifications
        """
        msg = await self._render_(to, subject, message, **kwargs)
        if 'attachments' in kwargs:
            for attach in kwargs['attachments']:
                self.add_attachment(
                    message=msg,
                    filename=attach
                )
        try:
            try:
                response = await self._server.send_message(msg)
                if self._debug is True:
                    self._logger.debug(response)
            except aiosmtplib.errors.SMTPServerDisconnected as err:
                raise RuntimeError(
                    f'{self.__name__} Server Disconnected {err}'
                ) from err
            return response
        except Exception as e:
            print('AQUI ERROR: ', e)
            self._logger.exception(e)
            raise ProviderError(
                f'{self.__name__} Error: got {e.__class__}, {e}'
            ) from e

    async def send(
            self,
            recipient: list[Actor] = None,
            message: Union[str, Any] = None,
            subject: str = None,
            **kwargs
        ):
        result = None
        # making the connection to the service:
        if not self._server:
            try:
                if asyncio.iscoroutinefunction(self.connect):
                    await self.connect()
                else:
                    self.connect()
            except Exception as err:
                raise ProviderError(
                    f"Error connecting to Mail Backend: {err}"
                ) from err
        # after connection, proceed exactly like other connectors.
        try:
            result = await super(ProviderEmail, self).send(recipient, message, subject=subject, **kwargs)
        except Exception as err:
            raise ProviderError(
                f"Error sending Email: {err}"
            ) from err
        return result
