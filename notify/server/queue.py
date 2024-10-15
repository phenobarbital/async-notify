from typing import Union, Any
from collections.abc import Callable, Awaitable
import time
import asyncio
import importlib
from navconfig.logging import logging
from notify.conf import (
    NOTIFY_QUEUE_SIZE,
    NOTIFY_QUEUE_CALLBACK
)
from notify.exceptions import NotifyException


class QueueManager:
    """Queue Manager for managing asyncio queue for Messages.
    """

    def __init__(self):
        self.logger = logging.getLogger('Notify.Queue')
        self.queue: asyncio.Queue = asyncio.Queue(
            maxsize=NOTIFY_QUEUE_SIZE
        )
        self.consumers: list = []
        self.logger.debug(
            f'Started Queue Manager with size: {NOTIFY_QUEUE_SIZE}'
        )
        ### Getting Queue Callback (called when queue object is consumed)
        self._callback: Union[Callable, Awaitable] = self.get_callback(
            NOTIFY_QUEUE_CALLBACK
        )
        self.logger.notice(
            f'Callback Queue: {self._callback!r}'
        )

    async def fire_consumers(self):
        """Fire up the Task consumers."""
        for _ in range(NOTIFY_QUEUE_SIZE - 1):
            task = asyncio.create_task(
                self.queue_handler()
            )
            self.consumers.append(task)

    def size(self):
        return self.queue.qsize()

    def empty(self):
        return self.queue.empty()

    def full(self):
        return self.queue.full()

    async def task_callback(self, task, **kwargs):
        self.logger.notice(
            f'Message Consumed >>> {task!r}'
        )

    def get_callback(self, done_callback: str) -> Union[Callable, Awaitable]:
        if not done_callback:
            ## returns a simple logger:
            return self.task_callback
        try:
            parts = done_callback.split(".")
            bkname = parts.pop()
            classpath = ".".join(parts)
            module = importlib.import_module(classpath, package=bkname)
            return getattr(module, bkname)
        except ImportError as ex:
            raise RuntimeError(
                f"Error loading Queue Callback {done_callback}: {ex}"
            ) from ex

    async def empty_queue(self):
        """Processing and shutting down the Queue."""
        while not self.queue.empty():
            self.queue.get_nowait()
            self.queue.task_done()
        await self.queue.join()
        # also: cancel the idle consumers:
        for c in self.consumers:
            try:
                c.cancel()
            except asyncio.CancelledError:
                pass

    # Queue Operations:
    async def put(self, task: Any, id: str):
        """put.

            Add a Task into the Queue.
        Args:
            task (Any): an instance of Message or Task
            id (str): the id of the Task
        """
        try:
            # asyncio.create_task(self.queue.put(task))
            await self.queue.put(task)
            await asyncio.sleep(.1)
            self.logger.info(
                f'Message {task!s} was queued with id {id} at {int(time.time())}'
            )
            # TODO: Add broadcast event for queued task.
            return True
        except asyncio.queues.QueueFull:
            self.logger.error(
                f"Notify Queue is Full, discarding Task {task!r}"
            )
            raise

    async def get(self) -> Any:
        """get.

            Get a Task from Queue.
        Returns:
            task (QueueWrapper): an instance of QueueWrapper
        """
        task = await self.queue.get()
        self.logger.info(
            f'Getting Task {task!s} at {int(time.time())}'
        )
        return task

    async def queue_handler(self):
        """Method for handling the tasks received by the connection handler."""
        while True:
            result = None
            message = await self.queue.get()
            self.logger.notice(
                f"Message started {message}"
            )
            ### Process Message:
            try:
                result = await message()
                if isinstance(result, asyncio.TimeoutError):
                    raise result
                elif isinstance(result, BaseException):
                    raise result
                self.logger.debug(
                    f'Consumed Message: {message} at {int(time.time())}'
                )
            except RuntimeError as exc:
                result = exc
                raise NotifyException(
                    f"Error: {exc}"
                ) from exc
            except Exception as exc:
                self.logger.error(
                    f"Message failed with error: {exc}"
                )
                raise
            finally:
                ### Task Completed
                self.queue.task_done()
                await self._callback(
                    message, result=result
                )
                await asyncio.sleep(.1)
