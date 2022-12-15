"""Abstract.

Base Factory classes for all kind of Providers.
"""
import asyncio
import time
from abc import ABC, abstractmethod
from enum import Enum
from functools import partial
from concurrent.futures import ThreadPoolExecutor
from typing import (
    Any,
    Union
)
from collections.abc import Awaitable, Callable
from navconfig.logging import logging
from notify.utils import SafeDict, cPrint
from notify.exceptions import ProviderError, MessageError
from notify.models import Actor
from notify.settings import NAVCONFIG, DEBUG


class ProviderType(Enum):
    NOTIFY = 'notify'  # generic notification
    SMS = 'sms'  # SMS messages
    EMAIL = 'email'  # email (smtp) notifications
    PUSH = 'push'  # push notifications
    IM = 'im'  # instant messaging


class ProviderBase(ABC):
    """ProviderBase.

    Base class for All providers
    """
    provider: str = None
    provider_type: ProviderType = ProviderType.NOTIFY
    blocking: bool = True
    sent: Callable = None

    def __init__(self, **kwargs):
        self.__name__ = str(self.__class__.__name__)
        self._params = kwargs
        self._logger = logging.getLogger('Notify')
        # environment config
        self._config = NAVCONFIG
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
        # add the Jinja Template Parser
        try:
            from notify import TemplateEnv # pylint: disable=C0415
            self._tpl = TemplateEnv
            self._template = None
        except Exception as err:
            raise RuntimeError(
                f"Notify: Can't load the Jinja2 Template Parser: {err}"
            ) from err
        # set the values of attributes:
        for arg, val in self._params.items():
            try:
                object.__setattr__(self, arg, val)
            except AttributeError:
                pass


### Async Context magic Methods
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
        except Exception as err: # pylint: disable=W0703
            logging.error(err)

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            self.close()
        except Exception as err: # pylint: disable=W0703
            logging.error(err)

    @abstractmethod
    async def connect(self, *args, **kwargs):
        pass

    @abstractmethod
    async def close(self):
        pass

    @abstractmethod
    async def _send_(self, to: Actor, message: Union[str, Any], subject: str = None, **kwargs) -> Any:
        """_send_.
          Method called for every recipient in Recipient list.
        Args:
            to (Actor): recipient of message.
            message (Union[str, Any]): message data.

        Raises:
            RuntimeError: Error when _send_ can be executed.

        Returns:
            Any: Result of sending process.
        """

    @classmethod
    def name(cls):
        return cls.__name__

    @classmethod
    def type(cls):
        return cls.provider_type

    def get_loop(self):
        return self._loop

    def set_loop(self, loop: asyncio.AbstractEventLoop = None):
        if not loop:
            self._loop = asyncio.new_event_loop()
        else:
            self._loop = loop
        asyncio.set_event_loop(self._loop)

    async def _prepare_(
            self,
            recipient: Actor = None,
            message: Union[str, Any] = None,
            template: str = None,
            **kwargs
        ): # pylint: disable=W0613
        """
        _prepare.

        Prepare a Message for Sending.
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

    async def _render_(
            self,
            to: Actor = None,
            message: str = None,
            subject: str = None,
            **kwargs
        ): # pylint: disable=W0613
        """
        _render_.

        Returns the parseable version of Message template.
        """
        # cPrint(f'RECEIVED {to}, message {message}')
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

    def create_task(self, to, message, loop: asyncio.AbstractEventLoop, subject: str = None, **kwargs):
        asyncio.set_event_loop(loop)
        task = loop.create_task(self._send_(to, message, subject=subject, **kwargs))
        fn = partial(self.__sent__, to, message, **kwargs)
        task.add_done_callback(fn)
        return task

    async def send(
            self,
            recipient: list[Actor] = None,
            message: Union[str, Any] = None,
            subject: str = None,
            **kwargs
        ):
        """
        send.

        public method to send messages and notifications
        """
        # template (or message) for preparation
        msg = await self._prepare_(
            recipient=recipient,
            message=message,
            **kwargs
        )
        rcpt = []
        results = None
        if isinstance(recipient, list):
            rcpt = recipient
        else:
            rcpt.append(recipient)
        # TODO: non-blocking code
        if self.blocking is True:
            loop = asyncio.new_event_loop()
            tasks = []
            for to in rcpt:
                task = self.create_task(to, msg, loop, subject, **kwargs)
                tasks.append(task)
            # creating the executor
            fn = partial(
                self.execute_notify, loop, tasks
            )
            with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
                results = loop.run_in_executor(pool, fn)
        else:
            asyncio.set_event_loop(self._loop)
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
                task = self.create_task(to, message, self._loop, subject, **kwargs)
                tasks.append(task)
                i += 1
            # send tasks to queue processor (producer)
            await asyncio.gather(*[self.notify_producer(queue, tasks)])
            # wait until the consumer has processed all items
            await queue.join()
            total_slept = time.monotonic() - started_at
            # Cancel our worker tasks.
            for task in consumers:
                task.cancel()
            print(f'System ended: {total_slept}')

        return results

    # PUB/SUB Logic based on Asyncio Queues
    async def notify_producer(self, queue, tasks: list):
        """
        Process Notify.
        Fill the asyncio Queue with tasks
        """
        for task in tasks:
            await queue.put(task)

    async def process_notify(self, queue):
        """
        Consumer logic of Asyncio Queue
        """
        while True:
            # Get a "work item" out of the queue.
            task = await queue.get()
            # process the task
            try:
                await task
            except (ProviderError, MessageError) as ex:
                logging.error(ex)
                raise
            finally:
                # Notify the queue that the item has been processed
                queue.task_done()

    def execute_notify(
            self,
            loop: asyncio.AbstractEventLoop,
            tasks: list[Awaitable]
            ):
        """
        execute_notify.
        Executing notification in a event loop.
        """
        asyncio.set_event_loop(loop)
        try:
            group = asyncio.gather(*tasks, return_exceptions=True)
            try:
                results = loop.run_until_complete(group)
                return results
            except RuntimeError as err:
                raise RuntimeError(
                    f"Notify: Error executing Notify: {err}"
                ) from err
            except Exception as err:
                logging.exception(err, stack_info=True)
                raise ProviderError(
                    f"Notify: Error executing Notify: {err}"
                ) from err
        except Exception as err:
            raise ProviderError(
                f"Notify: Exception on Notify: {err}"
            ) from err

    def __sent__(
                self,
                recipient: Actor,
                message: str,
                _task: Awaitable,
                **kwargs
            ):
        """
        processing the callback for every notification that we sent.
        """
        if callable(self.sent):
            try:
                result = _task.result()
                # logging:
                self._logger.debug(
                    f'Notification sent to:> {recipient}'
                )
                evt = asyncio.new_event_loop()
                if 'task' in kwargs:
                    del kwargs['task']
                fn = partial(self.callback_sent, recipient, message, result, evt, **kwargs)
                with ThreadPoolExecutor(max_workers=1) as executor:
                    evt.run_in_executor(executor, fn)
            except (AttributeError, RuntimeError) as ex:
                self._logger.exception(
                    f'Notify: *Sent* Function fail with error {ex}'
                )

    def callback_sent(
            self,
            recipient: Actor,
            message: Any,
            result: Any,
            evt: asyncio.AbstractEventLoop,
            **kwargs
        ) -> None:
        """callback_sent.

        Function for running Callback in a Thread.
        """
        asyncio.set_event_loop(evt)
        fn = partial(self.sent, recipient, message, result, **kwargs)
        try:
            if asyncio.iscoroutinefunction(self.sent):
                evt.run_until_complete(fn)
            else:
                fn()
        except (asyncio.CancelledError, asyncio.TimeoutError) as ex:
            logging.warning(ex)
        except RuntimeError as ex:
            print(ex)
            raise RuntimeError(
                f"Error calling Callback function: {ex}"
            ) from ex
        except Exception as ex: # pylint: disable=W0703
            print(ex)
            logging.exception(ex, stack_info=False)


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
