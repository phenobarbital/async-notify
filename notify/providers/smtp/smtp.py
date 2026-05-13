## for abstract email provider:
import ssl
from collections.abc import Callable
import smtplib
from notify.models import Actor
from notify.exceptions import ProviderError
# abstract class
from notify.providers.base import ProviderBase, ProviderType
from notify.providers import _mime_utils as _mu
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

    def _render_(
        self, to: Actor = None, message: str = None, subject: str = None, **kwargs
    ):
        """Build a UTF-8-safe multipart/alternative message (sync variant).

        Delegates envelope construction and part attachment to
        :mod:`_mime_utils`.  This method is synchronous (uses
        ``self._template.render(...)`` not ``render_async``).

        Args:
            to: Recipient Actor (or list of addresses).
            message: Plain-text body content.
            subject: Email subject line.
            **kwargs: Additional template arguments.

        Returns:
            A :class:`email.mime.multipart.MIMEMultipart` ready for transport.
        """
        sender = getattr(self, "actor", None) or self.username
        recipient = (
            to.account.address if not isinstance(to, list)
            else ", ".join(to)
        )
        msg = _mu.build_alternative_message(
            sender=sender,
            to=recipient,
            subject=subject,
        )
        # NOTE: smtp.py historically did NOT set msg["sender"] (it was
        # commented out at the original line ~193). Intentional asymmetry
        # with mail.py — preserved per spec §7 Risk #1.
        # preamble must be ASCII (fallback for non-MIME clients); empty is safe.
        msg.preamble = ""

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
            content = self._template.render(**self._templateargs)
        else:
            content = message
        _mu.attach_text_part(msg, content or "", "html")
        return msg

    def add_attachment(self, message, filename, mimetype="octect-stream"):
        """Attach a file to *message* with RFC 2231 filename encoding.

        The ``mimetype`` parameter is accepted for backwards-compatibility.
        The historically misspelled default ``"octect-stream"`` is treated as
        unknown and resolved via ``mimetypes.guess_type``.

        Args:
            message: The :class:`email.mime.multipart.MIMEMultipart` envelope.
            filename: Filesystem path to the file to attach.
            mimetype: Optional MIME type string.  The misspelled legacy
                default ``"octect-stream"`` is treated as absent.
        """
        resolved = (
            None
            if mimetype in ("octect-stream", "application/octet-stream")
            else mimetype
        )
        _mu.attach_file(message, filename, resolved)

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
