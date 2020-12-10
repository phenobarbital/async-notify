"""
Amazon AWS Email.

Sending amazon Emails using SMTP services
"""
from notify.providers import ProviderEmailBase, EMAIL
from notify.settings import (
    EMAIL_USERNAME, EMAIL_PASSWORD, EMAIL_PORT, EMAIL_HOST
    )
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

class Aws_email(ProviderEmailBase):
    """ AWS-based Email Provider
    :param username: Email client username
    :param password: Email client password
    """
    provider = 'aws_email'
    provider_type = EMAIL
    _port = 587
    _host = 'email-smtp.eu-west-1.amazonaws.com'
    _server = None
    _template = None
    context = None

    def __init__(self, username=None, password=None, *args, **kwargs):
        """
        Init.

        """
        super(Aws_email, self).__init__(*args, **kwargs)

        # connection related settings
        self.username = username
        if self.username is None:
            self.username = EMAIL_USERNAME

        self.password = password
        if self.password is None:
            self.password = EMAIL_PASSWORD

        if self.username is None or self.password is None:
            raise RuntimeWarning(
                'to send emails via {0} you need to configure username & password. \n'
                'Either send them as function argument via key \n'
                '`username` & `password` or set up env variable \n'
                'as `EMAIL_USERNAME` & `EMAIL_PASSWORD`.'.format(self.name)
            )
        if kwargs['account']:
            self.actor = kwargs['account']
        else:
            self.actor = self.username
        # server information
        try:
            self._host = kwargs['host']
        except KeyError:
            self._host = EMAIL_HOST
        try:
            self._port = kwargs['port']
        except KeyError:
            self._port = EMAIL_PORT
        try:
            self._server = self._make_connection()
        except Exception as e:
            return e

    @property
    def user(self):
        return self.username

    def _make_connection(self):
        """
        Making Connection
        """
        server = smtplib.SMTP(self._host, self._port)
        server.set_debuglevel(1)
        server.ehlo()
        server.starttls()
        server.login(self.username, self.password)
        return server

    def _prepare_message(self, to_address, subject, context):
        """
        """
        s = NotifyMessage(template=context['template'], context=context).content()
        message = MIMEMultipart('alternative')
        message['From'] = self.actor
        if isinstance(to_address, list):
            message['To'] = ", ".join(to_address)
        else:
            message['To'] = to_address
        message['Subject'] = subject
        message['sender'] = self.actor
        message['html'] = s['html_content']
        message['text'] = s['text_content']
        message.preamble = subject
        message.attach(MIMEText(s['text_content'], 'plain'))
        message.attach(MIMEText(s['html_content'], 'html'))
        return message

    def send(self, recipient, verb, **kwargs):
        if kwargs['context']:
            self.context = kwargs['context']
        if not self.actor:
            raise TypeError(_("Actor not specified."))
        if not verb:
            raise TypeError(_("Verb not specified."))
        if not recipient:
            raise TypeError(_("Recipient not specified."))
        # get data
        data = self._prepare_message(recipient, verb, self.context)
        # making email connnection
        try:
            text = data.as_string()
            self._server.send_message(data)
            self._server.close()
        except Exception as e:
            return e
        finally:
            self._server.quit()
