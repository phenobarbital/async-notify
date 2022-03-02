"""
Google Mail (gmail).

Using gmail library to send Email Messages.
"""
from notify.providers.abstract import ProviderEmail
from notify.settings import GMAIL_USERNAME, GMAIL_PASSWORD
from notify.models import Actor

# 3rd party gmail support
import smtplib
from gmail import GMail as GMailWorker, Message

class Gmail(ProviderEmail):
    """
    Gmail.

        Gmail-based Email Provider.
    Args:
        :param username: Email client username
        :param password: Email client password
    """
    provider = 'gmail'
    blocking: bool = True

    def __init__(self, username: str = None, password: str = None, *args, **kwargs):
        super(Gmail, self).__init__(*args, **kwargs)

        # connection related settings
        self.username = username
        if username is None:
            self.username = GMAIL_USERNAME

        self.password = password
        if password is None:
            self.password = GMAIL_PASSWORD

        if self.username is None or self.password is None:
            raise RuntimeWarning(
                'to send emails via **{0}** you need to configure username & password. \n'
                'Either send them as function argument via key \n'
                '`username` & `password` or set up env variable \n'
                'as `GMAIL_USERNAME` & `GMAIL_PASSWORD`.'.format(self.provider)
            )
        self.actor = self.username

    def close(self):
        if self._server:
            try:
                self._server.close()
            except Exception as err:
                pass

    def connect(self):
        """
        connect.

        Making a connection to Gmail Servers
        """
        try:
            self._server = GMailWorker(
                self.username, self.password
            )
        except smtplib.SMTPAuthenticationError as err:
            raise Exception('Authentication Error: {}'.format(err))
        except Exception as err:
            raise RuntimeError(err)

    def _render(self, to: Actor, subject: str, content: str, **kwargs):
        """
        """
        msg = content
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
            try:
                msg = kwargs['body']
            except KeyError:
                msg = content
        # email
        email = {
            'subject': subject,
            'text': msg,
            'sender': self.actor,
            'to': to.account['address'],
            'html': msg
        }
        return Message(**email)

    async def _send(self, to: Actor, message: str, subject: str,  **kwargs):
        """
        _send.

        Logic associated with the construction of notifications
        """
        data = self._render(to, subject, message, **kwargs)
        # making email connnection
        try:
            return self._server.send(data)
        except Exception as e:
            raise RuntimeError(e)
