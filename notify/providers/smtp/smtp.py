## for abstract email provider:
import os
import ssl
import asyncio
from typing import Union, Any
from collections.abc import Callable
from email import encoders
# from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.utils import formatdate
import smtplib
from notify.models import Actor
from notify.exceptions import ProviderError
# abstract class
from notify.providers.base import ProviderBase, ProviderType
from notify.providers.message import ThreadMessage
from notify.conf import (
    EMAIL_SMTP_USERNAME,
    EMAIL_SMTP_PASSWORD,
    EMAIL_SMTP_HOST,
    EMAIL_SMTP_PORT,
)


class SMTP(ProviderBase):
    """
    ProviderSMTP.

    Provider using simple SMTP connection.
    """

    provider_type = ProviderType.EMAIL
    blocking: str = 'executor'
    timeout: int = 60

    def __init__(
        self,
        hostname: str = None,
        port: str = None,
        username: str = None,
        password: str = None,
        **kwargs,
    ):
        """ """
        self._attachments: list = []
        self.force_tls: bool = True
        self.username = None
        self.password = None
        self._server: Callable = None
        super(SMTP, self).__init__(**kwargs)
        # port
        self.host = hostname
        if not self.host:  # already configured
            self.host = EMAIL_SMTP_HOST
        # port
        self.port = port
        if not self.port:
            self.port = EMAIL_SMTP_PORT

        # connection related settings
        self.username = username
        if self.username is None:
            self.username = EMAIL_SMTP_USERNAME

        self.password = password
        if self.password is None:
            self.password = EMAIL_SMTP_PASSWORD

        if self.username is None or self.password is None:
            raise RuntimeWarning(
                f"to send messages via **{self._name}** you need to configure user & password. \n"
                "Either send them as function argument via key \n"
                "`username` & `password` or set up env variable \n"
                "as `EMAIL_USERNAME` & `EMAIL_PASSWORD`."
            )
        try:
            # sent from another account
            if "account" in kwargs:
                self.actor = kwargs["account"]
            else:
                self.actor = self.username
        except KeyError:
            self.actor = self.username

    @property
    def user(self):
        return self.username

    async def close(self):
        if self._server:
            try:
                self._server.quit()
            except smtplib.SMTPServerDisconnected:
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
            self._server = smtplib.SMTP(
                host=self.host, port=self.port
            )
            self._server.connect(self.host, self.port)
            self._server.set_debuglevel(0)
            try:
                try:
                    self._server.ehlo()
                except smtplib.SMTPHeloError as exc:
                    print(exc)
                if self._server.has_extn('STARTTLS'):
                    self._server.starttls(context=context)
                    self._server.ehlo()  # ehlo again after starttls
                # You can then authenticate yourself with ehlo() and login()
                if self.username and self.password:
                    self._server.login(self.username, self.password)
                self.logger.debug(
                    f":: {self.__name__}: Connected to: {self._server}"
                )
            except smtplib.SMTPAuthenticationError as err:
                raise RuntimeError(
                    f"{self.__name__} Error: Invalid credentials: {err}"
                ) from err
            except smtplib.SMTPServerDisconnected as err:
                raise RuntimeError(
                    f"{self.__name__} Server Disconnected: {err}"
                ) from err
        except smtplib.SMTPRecipientsRefused as err:
            raise RuntimeError(
                f"{self.__name__} Error: got SMTPRecipientsRefused: {err.recipients}"
            ) from err
        except (smtplib.SMTPException) as e:
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

    def _render_(
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
        # msg["sender"] = self.actor
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
            content = self._template.render(**self._templateargs)
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

    def _send_(
        self, to: Actor, message: str, subject: str, **kwargs
    ):  # pylint: disable=W0221
        """
        _send_.

        Logic associated with the construction of notifications
        """
        msg = self._render_(to, message, subject, **kwargs)
        if "attachments" in kwargs:
            for attach in kwargs["attachments"]:
                self.add_attachment(message=msg, filename=attach)
        try:
            try:
                response = self._server.send_message(msg)
                if self._debug is True:
                    self.logger.debug(response)
            except smtplib.SMTPServerDisconnected as err:
                raise RuntimeError(
                    f"{self.__name__} Server Disconnected {err}"
                ) from err
            return response
        except Exception as e:
            self.logger.exception(e)
            raise ProviderError(
                f"{self.__name__} Error: got {e.__class__}, {e}"
            ) from e
