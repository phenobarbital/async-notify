"""Abstract.

Base Factory classes for all kind of Providers.
"""
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
            self._logger.info('Notification sent to> {}'.format(recipient))
            self.sent(recipient, message, result, task)