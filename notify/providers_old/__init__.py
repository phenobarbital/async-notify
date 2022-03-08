# -*- coding: utf-8 -*-
import asyncio
import time
from functools import partial
import uuid
from abc import ABC, ABCMeta, abstractmethod
from typing import List, Dict, Optional, Union, Callable, Awaitable
from notify.exceptions import (
    ProviderError,
    NotImplementedError,
    notifyException
    )
from notify.models import Account, Actor
from enum import Enum
from notify.settings import NAVCONFIG, logging_notify, LOG_LEVEL
from notify.utils import colors, SafeDict
from concurrent.futures import ThreadPoolExecutor
from asyncdb.exceptions import (_handle_done_tasks, default_exception_handler,
                                shutdown)

# email system
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# logging system
import logging
from logging.config import dictConfig
dictConfig(logging_notify)

NOTIFY = 'notify'
SMS = 'sms'
EMAIL = 'email'
PUSH = 'push'
IM = 'im'


class ProviderType(Enum):
    NOTIFY = 'notify'
    SMS = 'sms'
    EMAIL = 'email'
    PUSH = 'push'
    IM = 'im'


class ProviderBase(ABC):
    """ProviderBase.

    Base class for All providers
    """

    __metaclass__ = ABCMeta
    provider: str = None
    provider_type: ProviderType = NOTIFY
    longrunning: bool = True
    _loop = None
    _debug: bool = False
    _params: dict = None
    _logger = None
    _config = None
    _tplenv = None
    _template = None
    _templateargs: dict = {}
    sent: Callable = None

    def __init__(self, *args, **kwargs):
        self._params = kwargs
        self._logger = logging.getLogger('Notify')
        self._logger.setLevel(LOG_LEVEL)
        self._config = NAVCONFIG
        from notify import TemplateEnv
        self._tplenv = TemplateEnv
        for arg, val in self._params.items():
            try:
                object.__setattr__(self, arg, val)
            except AttributeError:
                pass
        if 'loop' in kwargs:
            self._loop = kwargs['loop']
            del kwargs['loop']
        else:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
        # configure debug:
        if 'debug' in kwargs:
            self._debug = kwargs['debug']
            del kwargs['debug']

    @abstractmethod
    def send(self, *args, **kwargs):
        pass

    @abstractmethod
    def connect(self, *args, **kwargs):
        pass

    @abstractmethod
    def close(self):
        pass

    def _prepare(self, recipient: Actor, message, template: str = None, **kwargs):
        """
        _prepare.

        Prepare works in the preparation of message for sending.
        """
        #1 replacement of strings
        if self._params:
            msg = message.format_map(SafeDict(**self._params))
        else:
            msg = message
        if template:
            # using template parser:
            self._template = self._tplenv.get_template(template)
            #print(self._template.environment.list_templates())
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
            asyncio.set_event_loop(self._loop)
        else:
            self._loop = loop

    def _render(self, to: Actor, message, **kwargs):
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
        handler = partial(_handle_done_tasks, self._logger)
        task.add_done_callback()
        fn = partial(self.__sent__, to, message)
        task.add_done_callback(fn)
        return task

    async def send(self, recipient: List[Actor] = [], message: str = '', **kwargs):
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
        if self.longrunning is True:
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
            # working on a asyncio.queue functionality
            queue = asyncio.Queue(maxsize=len(rcpt)+1)
            started_at = time.monotonic()
            tasks = []
            consumers = []
            i = 0
            for to in rcpt:
                # create the consumers:
                consumer = asyncio.create_task(self.process_notify(queue))
                consumers.append(consumer)
                # create the task:
                task = self.create_task(to, message, **kwargs)
                tasks.append(task)
                i += 1
            # send tasks to queue processor (producer)
            await self.notify_producer(queue, tasks)
            # wait until the consumer has processed all items
            await queue.join()
            total_slept_for = time.monotonic() - started_at
            # Cancel our worker tasks.
            for task in consumers:
                task.cancel()
            #print(f'{i} workers works in parallel for {total_slept_for:.2f} seconds')
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
            self._logger.info('Notification sent to> {}'.format(recipient))
            self.sent(recipient, message, result, task)


class ProviderEmailBase(ProviderBase):
    """
    ProviderEmailBase.

    Base class for All Email providers
    """

    provider_type = EMAIL
    _server = None

    async def send(
            self,
            recipient: List[Actor] = [],
            message: str = '',
            **kwargs
            ):
        result = None
        # making the connection to the service:
        try:
            if asyncio.iscoroutinefunction(self.connect):
                if not self.is_connected():
                    await self.connect()
            else:
                self.connect()
        except Exception as err:
            raise RuntimeError(err)
        # after connection, proceed exactly like other connectors.
        try:
            result = await super(ProviderEmailBase, self).send(recipient, message, **kwargs)
        except Exception as err:
            raise RuntimeError(err)
        return result


class ProviderMessageBase(ProviderBase):
    """ProviderMessageBase.

    Base class for All Message providers

    """
    provider_type = SMS


class ProviderIMBase(ProviderBase):
    """ProviderIMBase.

    Base class for All Message to Instant messenger providers

    """
    provider_type = IM
    _response = None
