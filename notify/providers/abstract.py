"""Abstract.

Base Factory classes for all kind of Providers.
"""
import os
import ssl
import logging
import asyncio
import time
from abc import ABC, ABCMeta, abstractmethod
from enum import Enum
from functools import partial
from notify.settings import NAVCONFIG, logging_notify, LOG_LEVEL, DEBUG
from concurrent.futures import ThreadPoolExecutor
from typing import (
    Any,
    Callable,
    Union,
    List,
    Awaitable
)
from asyncdb.exceptions import (
    _handle_done_tasks,
    default_exception_handler,
)
from notify.utils import SafeDict
from notify.models import Actor
# logging system
import logging
from logging.config import dictConfig

## for abstract email provider:
import aiosmtplib
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.utils import formatdate
from email import encoders


dictConfig(logging_notify)


class ProviderType(Enum):
    NOTIFY = 'notify' # generic notification
    SMS = 'sms' # SMS messages
    EMAIL = 'email' # email (smtp) notifications
    PUSH = 'push' # push notifications
    IM = 'im' # instant messaging


class ProviderBase(ABC, metaclass=ABCMeta):
    """ProviderBase.

    Base class for All providers
    """
    provider: str = None
    provider_type: ProviderType = ProviderType.NOTIFY
    blocking: bool = True
    sent: Callable = None

    def __init__(self, *args, **kwargs):
        self._params = kwargs
        self._logger = logging.getLogger('Notify')
        self._logger.setLevel(LOG_LEVEL)
        # environment config
        self._config = NAVCONFIG
        # add the Jinja Template Parser
        try:
            from notify import TemplateEnv
            self._tpl = TemplateEnv
            self._template = None
        except Exception as err:
            raise RuntimeError("Notify: Can't load the Jinja2 Template Parser.")
        # set the values of attributes:
        for arg, val in self._params.items():
            try:
                object.__setattr__(self, arg, val)
            except AttributeError:
                pass
        if 'loop' in kwargs:
            self._loop = kwargs['loop']
            del kwargs['loop']
        else:
            self._loop = asyncio.get_event_loop()
        asyncio.set_event_loop(self._loop)
        # configure debug:
        if 'debug' in kwargs:
            self._debug = kwargs['debug']
            del kwargs['debug']
        else:
            self._debug = DEBUG
            
    """
    Async Context magic Methods
    """
    async def __aenter__(self) -> "ProviderBase":
        if asyncio.iscoroutinefunction(self.connect):
            await self.connect()
        else:
            self.connect()
        return self
    
    def __enter__(self) -> "ProviderBase":
        self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        # clean up anything you need to clean up
        try:
            if asyncio.iscoroutinefunction(self.close):
                await self.close()
            else:
                self.close()
        except Exception as err:
            logging.error(err)
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            self.close()
        except Exception as err:
            logging.error(err)

    @abstractmethod
    def send(self, *args, **kwargs):
        pass

    @abstractmethod
    def connect(self, *args, **kwargs):
        pass

    @abstractmethod
    def close(self):
        pass

    def _prepare(self, recipient: Actor, message: Union[str, Any], template: str = None, **kwargs):
        """
        _prepare.

        works in the preparation of message for sending.
        """
        #1 replacement of strings
        if self._params:
            msg = message.format_map(
                SafeDict(**self._params)
            )
        else:
            msg = message
        if template:
            # using a template parser:
            self._template = self._tpl.get_template(template)
        else:
            self._template = None
        return msg

    @classmethod
    def name(self):
        return self.__name__

    @classmethod
    def type(self):
        return self.provider_type

    def get_loop(self):
        return self._loop

    def set_loop(self, loop=None):
        if not loop:
            self._loop = asyncio.new_event_loop()
        else:
            self._loop = loop
        asyncio.set_event_loop(self._loop)

    def _render(self, to: Actor, message: Union[str, Any], **kwargs):
        """
        _render.

        Returns the parseable version of template.
        """
        msg = message
        if self._template:
            self._templateargs = {
                "recipient": to,
                "username": to,
                "message": message,
                **kwargs
            }
            msg = self._template.render(**self._templateargs)
        return msg

    def create_task(self, to, message, **kwargs):
        task = asyncio.create_task(self._send(to, message, **kwargs))
        task.add_done_callback(_handle_done_tasks)
        fn = partial(self.__sent__, to, message)
        task.add_done_callback(fn)
        return task

    async def send(self, recipient: List[Actor] = [], message: Union[str, Any] = '', **kwargs):
        """
        send.

        public method to send messages and notifications
        """
        # template (or message) for preparation
        msg = self._prepare(recipient, message, **kwargs)
        rcpt = []
        if isinstance(recipient, list):
            rcpt = recipient
        else:
            rcpt.append(recipient)
        # working on Queues or executor:
        if self.blocking is True:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.set_exception_handler(default_exception_handler)
            tasks = []
            for to in rcpt:
                task = self.create_task(to, message, **kwargs)
                tasks.append(task)
            # creating the executor
            fn = partial(self.execute_notify, loop, tasks, **kwargs)
            with ThreadPoolExecutor(max_workers=10) as pool:
                result = loop.run_in_executor(pool, fn)
        else:
            # migrate to a non-blocking code, also, add a Queue system (started in paralell)
            # working on a asyncio.queue functionality
            queue = asyncio.Queue(maxsize=len(rcpt)+1)
            started_at = time.monotonic()
            tasks = []
            consumers = []
            i = 0
            for to in rcpt:
                # create the consumers:
                consumer = asyncio.create_task(
                    self.process_notify(queue)
                )
                consumers.append(consumer)
                # create the task:
                task = self.create_task(to, message, **kwargs)
                tasks.append(task)
                i+=1
            # send tasks to queue processor (producer)
            await self.notify_producer(queue, tasks)
            # wait until the consumer has processed all items
            await queue.join()
            total_slept_for = time.monotonic() - started_at
            # Cancel our worker tasks.
            for task in consumers:
                task.cancel()
        return True

    # PUB/SUB Logic based on Asyncio Queues
    async def notify_producer(self, queue, tasks: list):
        """
        Process Notify.

        Fill the asyncio Queue with tasks
        """
        for task in tasks:
            queue.put_nowait(task)

    async def process_notify(self, queue):
        """
        Consumer logic of Asyncio Queue
        """
        while True:
            # Get a "work item" out of the queue.
            task = await queue.get()
            # process the task
            await task
            # Notify the queue that the item has been processed
            queue.task_done()
            #print(f'{name} has slept for {1:.2f} seconds')

    def execute_notify(
        self,
        loop: asyncio.AbstractEventLoop,
        tasks: List[Awaitable],
        **kwargs
        ):
        """
        execute_notify.

        Executing notification in a event loop.
        """
        try:
            group = asyncio.gather(*tasks, loop=loop, return_exceptions=False)
            try:
                results = loop.run_until_complete(group)
            except (RuntimeError, Exception) as err:
                raise Exception(err)
                #TODO: Processing accordly the exceptions (and continue)
                # for task in tasks:
                #     if not task.done():
                #         await asyncio.gather(*tasks, return_exceptions=True)
                #         task.cancel()
        except Exception as err:
            raise Exception(err)

    def __sent__(
        self,
        recipient: Actor,
        message: str,
        task: Awaitable,
        **kwargs
        ):
        """
        processing the callback for every notification that we sent.
        """
        result = task.result()
        if callable(self.sent):
            # logging:
            self._logger.debug('Notification sent to> {}'.format(recipient))
            self.sent(recipient, message, result, task)


class ProviderEmail(ProviderBase):
    """
    ProviderEmail.

    Base class for All Email-based providers
    """

    provider_type = ProviderType.EMAIL
    _server: Callable = None
    
    def __init__(self, *args, **kwargs):
        self._name = self.__class__.__name__
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
                logging.debug(f'{self._name}: Connected to: {self._server}')
                try:
                    if self._server.is_ehlo_or_helo_needed:
                        await self._server.ehlo()
                except aiosmtplib.errors.SMTPHeloError:
                    pass
                await asyncio.sleep(0)
            except aiosmtplib.errors.SMTPAuthenticationError as err:
                raise RuntimeError(
                    f'{self._name} Error: Invalid credentials: {err}'
                )
            except aiosmtplib.errors.SMTPServerDisconnected as err:
                raise RuntimeError(f'{self._name} Error: {err}')
        except aiosmtplib.SMTPRecipientsRefused as e:
            raise RuntimeError(
                f'{self._name} Error: got SMTPRecipientsRefused: {e.recipients}'
            )
        except (OSError, aiosmtplib.errors.SMTPException) as e:
            raise RuntimeError(
                f'{self._name} Error: got {e.__class__}, {e}'
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
            html = None
        if html:
            message.add_header('Content-Type','text/html')
            #message.add_header('Content-Type: multipart/mixed')
            #message.add_header('Content-Transfer-Encoding: base64')
            message.attach(MIMEText(html, 'html'))
            #message.set_payload(html)
        return message

    def _render(self, to: Actor, subject: str, content: str, **kwargs):
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
            message['To'] = to.account['address']
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
        file = os.path.basename(filename)
        part.add_header(
            'Content-Disposition', 'attachment', filename=str(file)
        )
        message.attach(part)

    async def _send(self, to: Actor, message: str, subject: str,  **kwargs):
        """
        _send.

        Logic associated with the construction of notifications
        """
        msg = self._render(to, subject, message, **kwargs)
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
                raise RuntimeError(f'{self._name} Server Disconnected {err}')
            return response
        except Exception as e:
            print(e)
            raise RuntimeError(f'{self._name} Error: got {e.__class__}, {e}')

    async def send(
            self,
            recipient: List[Actor] = [],
            message: Union[str, Any] = None,
            **kwargs
        ):
        result = None
        # making the connection to the service:
        try:
            if asyncio.iscoroutinefunction(self.connect):
                await self.connect()
            else:
                self.connect()
        except Exception as err:
            raise RuntimeError(err)
        # after connection, proceed exactly like other connectors.
        try:
            result = await super(ProviderEmail, self).send(recipient, message, **kwargs)
        except Exception as err:
            raise RuntimeError(err)
        return result

class ProviderMessaging(ProviderBase):
    """ProviderMessaging.

    Base class for All Messaging Service providers (like SMS).

    """
    provider_type = ProviderType.SMS


class ProviderIM(ProviderBase):
    """ProviderIM.

    Base class for All Message to Instant messenger providers

    """
    provider_type = ProviderType.IM
    _response = None
    
class ProviderPush(ProviderBase):
    """ProviderPush.

    Base class for All Message to Push Notifications.

    """
    provider_type = ProviderType.PUSH
    _response = None