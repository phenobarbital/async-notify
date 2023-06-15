import os
import asyncio
import socket
import signal
from collections.abc import Awaitable
from redis import asyncio as aioredis
import cloudpickle
from navconfig.logging import logging
from datamodel.parsers.json import json_decoder
from datamodel.exceptions import ParserError
from notify.conf import (
    NOTIFY_REDIS,
    NOTIFY_CHANNEL,
    NOTIFY_DEFAULT_HOST,
    NOTIFY_DEFAULT_PORT
)
from notify.exceptions import NotifyException
from .queue import QueueManager
from .wrapper import NotifyWrapper


DEFAULT_HOST = NOTIFY_DEFAULT_HOST
if not DEFAULT_HOST:
    DEFAULT_HOST = socket.gethostbyname(socket.gethostname())


class NotifyWorker:
    """NotifyWorker.

    Can be used to dispatch notifications using a Redis Broker or directly messages.
    Attributes:
        host: Hostname for listening service.
        port: Port number of the server.
        debug: enable debug logging
    """
    def __init__(
            self,
            host: str = DEFAULT_HOST,
            port: int = NOTIFY_DEFAULT_PORT,
            debug: bool = False
    ):
        self.host = host
        self.port = port
        self.debug = debug
        self.queue = None
        self._server: Awaitable = None
        self._pid = os.getpid()
        self._new_evt = False
        self._running: bool = True
        try:
            self._loop = asyncio.get_event_loop()
        except RuntimeError:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._new_evt = True
        # May want to catch other signals too
        if hasattr(signal, "SIGHUP"):
            signals = (signal.SIGHUP, signal.SIGTERM)
        else:
            signals = (signal.SIGTERM)
        for s in signals:
            self._loop.add_signal_handler(
                s, lambda s=s: asyncio.create_task(self.stop())
            )

        # logging:
        self.logger = logging.getLogger(
            'Notify.Server'
        )

    def start_redis(self):
        self.pool = aioredis.ConnectionPool.from_url(
            NOTIFY_REDIS,
            encoding='utf8',
            decode_responses=True,
            max_connections=5000
        )
        self.redis = aioredis.Redis(connection_pool=self.pool)

    async def start_subscription(self):
        """Starts PUB/SUB system based on Redis."""
        try:
            self.pubsub = self.redis.pubsub()
            await self.pubsub.subscribe(NOTIFY_CHANNEL)

            while self._running:
                try:
                    msg = await self.pubsub.get_message()
                    if msg and msg['type'] == 'message':
                        self.logger.debug(f'Received message: {msg}')
                        message = self.build_notify(msg['data'])
                        await message()
                    await asyncio.sleep(0.001)  # sleep a bit to prevent high CPU usage
                except ConnectionResetError:
                    self.logger.error(
                        "Connection was closed, trying to reconnect."
                    )
                    await asyncio.sleep(1)  # Wait for a bit before trying to reconnect
                    await self.start_subscription()  # Try to restart the subscription
                except asyncio.CancelledError:
                    await self.pubsub.unsubscribe(NOTIFY_CHANNEL)
                    break
                except KeyboardInterrupt:
                    break
                except Exception as exc:
                    # Handle other exceptions as necessary
                    self.logger.error(
                        f"Error in start_subscription: {exc}"
                    )
                    break
        except Exception as exc:
            self.logger.error(
                f"Could not establish initial connection: {exc}"
            )

    async def start_server(self):
        server = await asyncio.start_server(
            self.connection_handler,
            host=self.host,
            port=self.port,
            family=socket.AF_INET,
            reuse_port=True
        )
        self.server_address = (
            socket.gethostbyname(socket.gethostname()), self.port
        )
        sock = server.sockets[0].getsockname()
        self.logger.info(
            f'Serving Notify Service on {sock}, pid: {self._pid}'
        )
        return server

    async def start(self):
        """Starts Service instance."""
        # Redis Service:
        self.start_redis()
        # Queue Manager.
        self.queue = QueueManager()
        # Subscription Manager:
        self.subscription_task = self._loop.create_task(
            self.start_subscription()
        )
        # and TCP Server:
        try:
            self._server = await self.start_server()
        except Exception as err:
            raise NotifyException(
                f"Error: {err}"
            ) from err
        try:
            await self.queue.fire_consumers()
            async with self._server:
                await self._server.serve_forever()
        except asyncio.CancelledError:
            print('::: Server was shutting down ::: ')
        except (RuntimeError) as err:
            self.logger.exception(
                err, stack_info=True
            )
            raise

    async def stop(self):
        self._running = False
        if self.debug is True:
            self.logger.debug(
                'Shutting down Notify Service.'
            )
        # forcing close the queue
        try:
            await self.queue.empty_queue()
        except KeyboardInterrupt:
            pass
        try:
            # Get a new pubsub object and unsubscribe from 'channel'
            try:
                await self.pubsub.unsubscribe(NOTIFY_CHANNEL)
                await asyncio.wait_for(self.redis.close(), timeout=2.0)
            except asyncio.TimeoutError:
                self.logger.error(
                    "Redis took too long to close."
                )
            await self.pool.disconnect(
                inuse_connections=True
            )
        except RuntimeError as err:
            self.logger.exception(
                err, stack_info=True
            )
        try:
            self.subscription_task.cancel()
            await self.subscription_task
        except asyncio.CancelledError:
            pass
        try:
            self._loop.set_debug(True)
            tasks = [
                task
                for task in asyncio.all_tasks(self._loop)
                if task is not asyncio.current_task() and not task.done()
            ]
            if tasks:
                # logging.warning(
                #     f"Cancelling {len(tasks)} outstanding tasks: {tasks}"
                # )
                for task in tasks:
                    task.cancel()
                # Now wait for all tasks to be cancelled:
                await asyncio.gather(*tasks, return_exceptions=True)
            self._server.close()
            await asyncio.wait_for(
                self._server.wait_closed(), timeout=5
            )
        except asyncio.CancelledError:
            pass
        except asyncio.TimeoutError:
            self.logger.error("Server closing due timed out.")
        except RuntimeError as err:
            self.logger.exception(
                err, stack_info=True
            )
        except Exception as exc:
            raise NotifyException(
                f"Error closing Notify Worker: {exc}"
            ) from exc
        finally:
            self.logger.debug(
                'Notify Service stopped.'
            )
            if self._new_evt is True:
                self._loop.close()

    async def _read_message(self, reader: asyncio.StreamReader):
        msg = b''
        while True:
            msg += await reader.read(-1)
            if reader.at_eof():
                break
        return msg

    def build_notify(self, data: dict):
        try:
            msg = json_decoder(data)
            return NotifyWrapper(**msg)
        except KeyError as ex:
            raise NotifyException(
                f"Missing Provider info on Message {msg}"
            ) from ex
        except ParserError as exc:
            self.logger.error(
                f"Unable to parse JSON message: {exc}"
            )
            raise

    async def connection_handler(
            self,
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter
    ):
        """ Handler for Function/Task Execution.
        receives the client request and run/queue the function.
        Args:
            reader: asyncio StreamReader, client information
            writer: asyncio StreamWriter, infor to send to client.
        """
        addr = writer.get_extra_info(
            "peername"
        )
        data = await self._read_message(reader)
        self.logger.info(
            f"Received Data from {addr!r} to Notify Service pid: {self._pid}"
        )
        try:
            message = self.build_notify(data)
            # Put message into queue:
            try:
                await self.queue.put(message, id=message.id)
                result = f'Message {message!s} was Queued with id {message.id}.'.encode('utf-8')
            except asyncio.QueueFull:
                return await self._discarded(
                    message=f'Message {message!s} was discarded, queue full',
                    writer=writer
                )
            await self.closing_writer(writer, result)
        except ParserError:
            ### Empty Task:
            ex = ParserError(
                "Error Decoding Serialized Message: {data!r}"
            )
            result = cloudpickle.dumps(ex)
            await self.closing_writer(writer, result)
            return False

    async def _discarded(self, message: str, writer: asyncio.StreamWriter):
        exc = NotifyException(
            message
        )
        result = cloudpickle.dumps(exc)
        await self.closing_writer(
            writer,
            result
        )
        return False

    async def closing_writer(self, writer: asyncio.StreamWriter, result):
        """Sending results and closing the streamer."""
        try:
            writer.write(result)
            await writer.drain()
            if writer.can_write_eof():
                writer.write_eof()
            writer.close()
        except Exception as e:
            self.logger.error(
                f"Error while closing writer: {str(e)}"
            )
