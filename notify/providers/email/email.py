# -*- coding: utf-8 -*-
import os
from notify.settings import EMAIL_USERNAME, EMAIL_PASSWORD, EMAIL_HOST, EMAIL_PORT
import pprint

import aiosmtplib
import asyncio
import ssl

from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.utils import formatdate
from email import encoders

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
    force_tls: bool = True
    longrunning: bool = False
    _attachments: list = []

    def __init__(self, hostname=None, port=None, username=None, password=None, **kwargs):
        """

        """
        super(Email, self).__init__(**kwargs)

        # server information
        self._host = hostname
        if self._host is None:
            try:
                self._host = kwargs['hostname']
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
                'to send messages via {0}need to configure user & password. \n'
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

    async def close(self):
        if self._server:
            try:
                await self._server.quit()
            except aiosmtplib.errors.SMTPServerDisconnected:
                pass
            except Exception as err:
                raise Exception(err)
            finally:
                self._server = None

    async def connect(self):
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
                hostname=self._host,
                port=self._port,
                username=self.username,
                password=self.password,
                start_tls=True,
                tls_context=context,
                loop=self._loop
            )
            try:
                await self._server.connect()
                try:
                    if self._server.is_ehlo_or_helo_needed:
                        await self._server.ehlo()
                except aiosmtplib.errors.SMTPHeloError:
                    pass
                await asyncio.sleep(0)
            except aiosmtplib.errors.SMTPAuthenticationError as err:
                raise RuntimeError(
                    'Email Error: Invalid credentials, error: {}'.format(err)
                )
            except aiosmtplib.errors.SMTPServerDisconnected as err:
                raise RuntimeError('Email Error: {}'.format(err))
        except aiosmtplib.SMTPRecipientsRefused as e:
            raise RuntimeError(
                'Email Error: got SMTPRecipientsRefused: {}'.format(e.recipients)
            )
        except (OSError, aiosmtplib.errors.SMTPException) as e:
            raise RuntimeError(
                'Email Error: got {}, {}'.format(e.__class__, str(e))
            )

    def is_connected(self):
        if self._server:
            return self._server.is_connected
        else:
            return False

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
        message['Date'] = formatdate(localtime=True)
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
        part.add_header(
            'Content-Disposition', 'attachment', filename=str(filename)
        )
        message.attach(part)

    async def _send(self, to: Actor, message: str, subject: str, **kwargs):
        """
        _send.

        Logic associated with the construction of notifications
        """
        msg = self._render(to, message, subject, **kwargs)
        if 'attachments' in kwargs:
            for attach in kwargs['attachments']:
                self.add_attachment(
                    message=msg,
                    filename=attach
                )
        # making email connnection
        if not self._server.is_connected:
            await self._server.connect()
            await self._server.login(
                username=self.username,
                password=self.password
            )
        try:
            try:
                response = await self._server.send_message(msg)
                if self._debug is True:
                    self._logger.debug(response)
            except aiosmtplib.errors.SMTPServerDisconnected as err:
                raise RuntimeError('Server Disconnected {}'.format(err))
            return response
        except Exception as e:
            print(e)
            raise RuntimeError('Email Error: got {}, {}'.format(e.__class__, str(e)))
