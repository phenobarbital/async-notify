# -*- coding: utf-8 -*-
import os
from notify.settings import EMAIL_USERNAME, EMAIL_PASSWORD, EMAIL_HOST, EMAIL_PORT
import pprint

import smtplib
import ssl


from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from notify.providers import ProviderEmailBase, EMAIL
from notify.models import Actor
from notify.utils import colors

class Email(ProviderEmailBase):
    """
    email.
    TODO: migrate to aiosmtplib
    """
    provider = 'email'
    provider_type = EMAIL
    _port = 587
    _host = 'email-smtp.eu-west-1.amazonaws.com'
    _server = None
    _template = None
    context = None

    def __init__(self, host=None, port=None, username=None, password=None, **kwargs):
        """
        """
        super(Email, self).__init__()

        # server information
        self._host = host
        if host is None:
            try:
                self._host = kwargs['host']
            except KeyError:
                self._host = EMAIL_HOST

        self._port = port
        if port is None:
            try:
                self._port = kwargs['port']
            except KeyError:
                self._port = EMAIL_PORT

        # connection related settings
        self.username = username
        if username is None:
            self.username = EMAIL_USERNAME

        self.password = password
        if self.password is None:
            self.password = EMAIL_PASSWORD



        if self.username is None or self.password is None:
            raise RuntimeWarning(
                'to send messages via {0} you need to configure username & password. \n'
                'Either send them as function argument via key \n'
                '`username` & `password` or set up env variable \n'
                'as `EMAIL_USERNAME` & `EMAIL_PASSWORD`.'.format(self.provider)
            )
        try:
            # sent from another account
            if kwargs['account']:
                self.actor = kwargs['account']
            else:
                self.actor = self.username
        except KeyError:
            self.actor = self.username

    @property
    def user(self):
        return self.username

    def __del__(self):
        self.close()

    def close(self):
        if self._server:
            try:
                self._server.quit()
            except smtplib.SMTPServerDisconnected:
                pass
            except Exception as err:
                raise Exception(err)
            finally:
                self._server = None

    def connect(self):
        """
        Make a connection to the SMTP Server
        """
        try:
            print('EMAIL: ', self._host, self._port, self.username, self.password)
            self._server = smtplib.SMTP(self._host, self._port)
            #self._server = smtplib.SMTP_SSL(self._host, self._port)
            if self._debug:
                self._server.set_debuglevel(1)
            try:
                self._server.ehlo()
            except smtplib.SMTPHeloError:
                self._server.ehlo_or_helo_if_needed()
            context = ssl.SSLContext(ssl.PROTOCOL_TLS)
            self._server.starttls(context=context)
            self._server.ehlo()
            try:
                self._server.login(self.username, self.password, initial_response_ok=True)
            except smtplib.SMTPAuthenticationError as err:
                raise RuntimeError('Email Error: Invalid credentials, error: {}'.format(err))
            except smtplib.SMTPServerDisconnected as err:
                raise RuntimeError('Email Error: {}'.format(err))
        except smtplib.SMTPRecipientsRefused as e:
            raise RuntimeError('Email Error: got SMTPRecipientsRefused: {}'.format(e.recipients))
        except (OSError, smtplib.SMTPException) as e:
            raise RuntimeError('Email Error: got {}, {}'.format(e.__class__, str(e)))


    def _prepare_message(self, to_address, message, content):
        """
        """
        if isinstance(content, dict):
            html = content['html']
            text = content['text']
        else:
            text = content
        if html:
            message.add_header('Content-Type','text/html')
            #message.add_header('Content-Type: multipart/mixed')
            #message.add_header('Content-Transfer-Encoding: base64')
            message.attach(MIMEText(html, 'html'))
            #message.set_payload(html)
        return message

    def _render(self, to: Actor, content: str, subject: str, **kwargs):
        """
        _render.

        Returns the parseable version of Email.
        """
        #TODO: add attachments
        message = MIMEMultipart('alternative')
        message['From'] = self.actor
        if isinstance(to, list):
            message['To'] = ", ".join(to)
        else:
            message['To'] = to.account['address']
        message['Subject'] = subject
        message['sender'] = self.actor
        message.preamble = subject
        if content:
            message.attach(MIMEText(content, 'plain'))
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
        message.add_header('Content-Type','text/html')
        #message.add_header('Content-Type', 'multipart/mixed')
        #message.add_header('Content-Transfer-Encoding', 'base64')
        message.attach(MIMEText(msg, 'html'))
        #message.set_payload(msg)
        return message

    async def _send(self, to: Actor, message: str, subject: str, **kwargs):
        """
        _send.

        Logic associated with the construction of notifications
        """
        data = self._render(to, message, subject, **kwargs)
        # making email connnection
        try:
            result = self._server.send_message(data)
            return result
        except Exception as e:
            print(e)
            raise RuntimeError('Email Error: got {}, {}'.format(e.__class__, str(e)))
