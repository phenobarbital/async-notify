"""Base.

Base Factory classes for all kind of Providers.
"""
import asyncio
from abc import ABC, abstractmethod
from typing import Any, Union, Optional
from collections.abc import Awaitable, Callable
from enum import Enum
from functools import partial
from concurrent.futures import ThreadPoolExecutor
from navconfig import DEBUG
from navconfig.logging import logging
from notify.types import SafeDict
from notify.exceptions import (
    ProviderError
)
from notify.models import Actor
from .message import ThreadMessage


class ProviderType(Enum):
    NOTIFY = "notify"  # generic notification
    SMS = "sms"  # SMS messages
    EMAIL = "email"  # email (smtp) notifications
    PUSH = "push"  # push notifications
    IM = "im"  # instant messaging


class ProviderBase(ABC):
    """ProviderBase.

    Base class for All providers
    """

    provider: str = None
    provider_type: ProviderType = ProviderType.NOTIFY
    blocking: bool = True
    sent: Optional[Union[Callable, Awaitable]] = None

    def __init__(self, *args, **kwargs):
        self.__name__ = str(self.__class__.__name__)
        self._args = args
        self._kwargs = kwargs
        self.logger = logging.getLogger(
            f"Notify.{self.__name__}"
        )
        # environment config
        if "loop" in kwargs:
            self._loop = kwargs["loop"]
            del kwargs["loop"]
            asyncio.set_event_loop(self._loop)
        else:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.get_event_loop()
        # configure debug:
        if "debug" in kwargs:
            self._debug = kwargs["debug"]
            del kwargs["debug"]
        else:
            self._debug = DEBUG
        # add the Jinja Template Parser
        try:
            from notify.notify import TemplateEnv  # pylint: disable=C0415
            self._tpl = TemplateEnv
            self._template = None
        except Exception as err:
            raise RuntimeError(
                f"Notify: Can't load the Jinja2 Template Parser: {err}"
            ) from err
        # set the values of attributes:
        for arg, val in kwargs.items():
            try:
                object.__setattr__(self, arg, val)
            except AttributeError:
                pass

    ### Async Context magic Methods
    async def __aenter__(self) -> "ProviderBase":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        # clean up anything you need to clean up
        try:
            await self.close()
        except Exception as err:  # pylint: disable=W0703
            self._logger.error(err)

    @abstractmethod
    async def connect(self, *args, **kwargs):
        pass

    @abstractmethod
    async def close(self):
        pass

    @classmethod
    def name(cls):
        return cls.__name__

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
        **kwargs,
    ):  # pylint: disable=W0613
        """
        _prepare.

        Prepare a Message for Sending.
        """
        if self._kwargs:
            msg = message.format_map(SafeDict(**self._kwargs))
        else:
            msg = message
        if template:
            # Getting Template from Template Parser.
            self._template = self._tpl.get_template(template)
        else:
            self._template = None
        return msg

    async def _render_(
        self, to: Actor = None, message: str = None, subject: str = None, **kwargs
    ):  # pylint: disable=W0613
        """
        _render_.

        Returns the parseable version of Message template.
        """
        msg = message
        if self._template:
            self._templateargs = {
                "recipient": to,
                "username": to,
                "message": message,
                "subject": subject,
                **kwargs,
            }
            msg = await self._template.render_async(**self._templateargs)
        return msg

    @abstractmethod
    async def _send_(
        self, to: Actor, message: Union[str, Any], subject: str = None, **kwargs
    ) -> Any:
        """_send_.
          Method called for every recipient on Recipient list.
        Args:
            to (Actor): recipient of message.
            message (Union[str, Any]): message data.
            subject (str): subject of message

        Raises:
            RuntimeError: Error when _send_ can be executed.

        Returns:
            Any: Result of sending process.
        """

    def __sent__(self, recipient: Actor, message: str, _task: Awaitable, **kwargs):
        """
        processing the callback for every notification that we sent.
        """
        if callable(self.sent):
            try:
                result = _task.result()
                # logging:
                self.logger.debug(
                    f"Notification sent to:> {recipient}"
                )
                try:
                    evt = asyncio.new_event_loop()
                    if "task" in kwargs:
                        del kwargs["task"]
                    fn = partial(
                        self.callback_sent,
                        recipient,
                        message,
                        result,
                        evt,
                        **kwargs
                    )
                    with ThreadPoolExecutor(max_workers=2) as executor:
                        evt.run_in_executor(
                            executor,
                            fn
                        )
                finally:
                    evt.close()
            except (AttributeError, RuntimeError) as ex:
                self.logger.error(
                    f"Notify: *Sent* Function fail with error {ex}"
                )

    def callback_sent(
        self,
        recipient: Actor,
        message: Any,
        result: Any,
        evt: asyncio.AbstractEventLoop,
        **kwargs,
    ) -> None:
        """callback_sent.

        Function for running Callback in a Thread.
        """
        asyncio.set_event_loop(evt)
        fn = partial(
            self.sent,
            recipient,
            message,
            result,
            **kwargs
        )
        try:
            if asyncio.iscoroutinefunction(self.sent):
                evt.run_until_complete(fn)
            else:
                fn()
        except (asyncio.CancelledError, asyncio.TimeoutError) as ex:
            self.logger.warning(ex)
        except RuntimeError:
            raise
        except Exception as ex:  # pylint: disable=W0703
            self.logger.exception(ex, stack_info=False)
            raise ProviderError(
                f"Error calling Callback function: {ex}"
            ) from ex

    async def send(
        self,
        recipient: list[Actor] = None,
        message: Union[str, Any] = None,
        subject: str = None,
        **kwargs,
    ):
        """
        send.

        public method to send messages and notifications
        """
        # template (or message) for preparation
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        message = await self._prepare_(
            recipient=recipient,
            message=message,
            **kwargs
        )
        results = None
        recipients = [recipient] if not isinstance(recipient, list) else recipient
        if self.blocking is False:
            # asyncio:
            tasks = []
            for to in recipients:
                task = loop.create_task(
                    self._send_(to, message, subject=subject, **kwargs)
                )
                fn = partial(self.__sent__, to, message, **kwargs)
                task.add_done_callback(fn)
                tasks.append(task)
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for idx, result in enumerate(results):
                if isinstance(result, Exception):
                    self.logger.warning(
                        f'Task {idx} raised exception: {result}'
                    )

        else:
            # is blocking, using threads and an asyncio queue
            msg_queue = asyncio.Queue()
            tasks = []
            for to in recipients:
                t = ThreadMessage(
                    self._send_,
                    self.__sent__,
                    msg_queue,
                    to,
                    message=message,
                    subject=subject,
                    **kwargs
                )
                t.start()
                tasks.append(t)
            # then run:
            results = []
            for t in tasks:
                t.join()
                if t.exc:
                    self.logger.warning(f'Error: {t.exc!s}')
                results.append(t.result)
            try:
                while not msg_queue.empty():
                    await msg_queue.get()
            except Exception as e:
                self.logger.error(
                    f"An unexpected error occurred: {str(e)}"
                )
        return results
