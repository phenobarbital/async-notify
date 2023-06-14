import asyncio
from typing import Any, Union
from collections.abc import Callable, Awaitable
from functools import partial
import threading
from notify.models import Actor


class ThreadMessage(threading.Thread):
    def __init__(
        self,
        fn: Union[Callable, Awaitable],
        callback: Union[Callable, Awaitable],
        queue: asyncio.Queue,
        rcpt: Actor,
        message: Any = None,
        subject: str = None,
        **kwargs
    ):
        super().__init__()
        self._loop = asyncio.new_event_loop()
        self._queue = queue
        self._message = message
        self._subject = subject
        self.exc = None
        self._fn = fn
        self._callback = callback
        self._rcpt = rcpt
        self._kwargs = kwargs
        self.result: Any = None

    def run(self):
        asyncio.set_event_loop(self._loop)
        try:
            task = self._loop.create_task(
                self._fn(
                    self._rcpt,
                    self._message,
                    subject=self._subject,
                    **self._kwargs
                )
            )
            fn = partial(self._callback, self._rcpt, self._message, **self._kwargs)
            task.add_done_callback(fn)
            self.result = self._loop.run_until_complete(
                task
            )
        except Exception as ex:  # pylint: disable=W0703
            self.exc = ex
        finally:
            self._loop.close()
