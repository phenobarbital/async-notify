from collections.abc import Awaitable, Callable
from typing import Optional, Union
import os
import base64
import asyncio
import time
import socket
import signal
import multiprocessing as mp
from redis import asyncio as aioredis
from redis.exceptions import ResponseError, ConnectionError
import cloudpickle
from navconfig.logging import logging
from datamodel.parsers.json import json_decoder
from datamodel.exceptions import ParserError
from notify.conf import (
    NOTIFY_REDIS,
    NOTIFY_CHANNEL,
    NOTIFY_WORKER_STREAM,
    NOTIFY_WORKER_GROUP,
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
        name: Name of the Worker.
        notify_empty_stream: Notify if the stream is empty.
        empty_stream_minutes: Number of minutes to wait before notifying.
    """
    send_notification: Optional[Union[Callable, Awaitable]] = None

    def __init__(
            self,
            host: str = DEFAULT_HOST,
            port: int = NOTIFY_DEFAULT_PORT,
            debug: bool = False,
            name: Optional[str] = None,
            notify_empty_stream: bool = False,
            empty_stream_minutes: int = 10
    ):
        self.host = host
        self.port = port
        self.debug = debug
        self.queue = None
        self._server: Awaitable = None
        self._pid = os.getpid()
        self._new_evt = False
        self._running: bool = True
        self._notify_empty_stream = notify_empty_stream
        self._empty_stream_minutes = empty_stream_minutes
        self.empty_stream_checker_task: Optional[Callable] = None
        if name:
            self._name = name
        else:
            self._name = mp.current_process().name
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

    async def cleanup_old_messages(self):
        """Removes messages older than 7 days from the stream."""
        try:
            # Calculate the timestamp for 7 days ago
            seven_days_ago = int(
                (time.time() - 7 * 24 * 60 * 60) * 1000
            )
            # Convert it to a Redis Stream ID format (timestamp-part-sequence)
            seven_days_ago_id = f"{seven_days_ago}-0"
            # Use XTRIM with minid to remove messages older than the calculated timestamp
            await self.redis.xtrim(NOTIFY_WORKER_STREAM, minid=seven_days_ago_id)
            self.logger.info(
                f"Notify: Cleaned up old messages from stream {NOTIFY_WORKER_STREAM}"
            )

        except Exception as e:
            self.logger.error(
                f"Notify: Error cleaning up old messages: {e}"
            )

    async def ensure_group_exists(self):
        try:
            # Try to create the group. This will fail if the group already exists.
            await self.redis.xgroup_create(
                NOTIFY_WORKER_STREAM,
                NOTIFY_WORKER_GROUP,
                id='$',
                mkstream=True
            )
        except ResponseError as e:
            if "BUSYGROUP Consumer Group name already exists" not in str(e):
                raise
        except Exception as exc:
            self.logger.exception(
                exc, stack_info=True
            )
            raise
        try:
            # create the consumer:
            await self.redis.xgroup_createconsumer(
                NOTIFY_WORKER_STREAM,
                NOTIFY_WORKER_GROUP,
                self._name
            )
            self.logger.debug(
                f":: Creating Consumer {self._name} on Stream {NOTIFY_WORKER_STREAM}"
            )
        except Exception as exc:
            self.logger.exception(
                exc,
                stack_info=True
            )
            raise

    async def check_stream_empty(self):
        """Checks if the stream is empty and sends a notification if it is."""
        while self._running:
            try:
                # Get the last message ID in the stream
                last_id = await self.redis.xrevrange(NOTIFY_WORKER_STREAM, count=1)

                if not last_id:
                    # Stream is empty, set a safe last message time far in the past
                    last_message_time = 0
                else:
                    # Extract the timestamp from the message ID
                    last_message_time = int(last_id[0][0].split('-')[0])

                # Get the current time in milliseconds
                current_time_ms = time.time() * 1000

                # Check if the stream has ever had messages to avoid huge numbers
                if last_message_time > 0:
                    # Calculate the time difference in minutes
                    time_diff_minutes = (current_time_ms - last_message_time) / 60000
                else:
                    # Indicate that the stream is empty and has no messages
                    time_diff_minutes = float('inf')

                if time_diff_minutes > self._empty_stream_minutes:
                    msg = f"Stream {NOTIFY_WORKER_STREAM} has been empty for {time_diff_minutes:.2f} minutes."
                    self.logger.warning(msg)
                    # TODO: Send log or email notification here
                    if callable(self.send_notification):
                        if asyncio.iscoroutinefunction(self.send_notification):
                            await self.send_notification(  # pylint: disable=E1102 # noqa
                                msg
                            )
                        else:
                            self.send_notification(  # pylint: disable=E1102 # noqa
                                msg
                            )
                # Check for emptyness every minute
                await asyncio.sleep(60)

            except Exception as e:
                self.logger.error(
                    f"Error checking stream: {e}"
                )
                # Wait a minute before trying again
                await asyncio.sleep(60)

    async def publish_subscribe(self):
        try:
            msg = await self.pubsub.get_message()
            if isinstance(msg, dict) and msg.get('type', None) == 'message':
                self.logger.debug(
                    f'Received message: {msg!s}'
                )
                message = self.build_notify(msg['data'])
                await message()
        except ConnectionResetError:
            self.logger.error(
                "Notify: Connection was closed, trying to reconnect."
            )
            # Wait for a bit before trying to reconnect
            await asyncio.sleep(1)
            raise
        except asyncio.CancelledError:
            await self.pubsub.unsubscribe(NOTIFY_CHANNEL)
            raise

    async def check_stream(self):
        """check_stream.

        Check if there is a Message in the Group Stream.
        """
        try:
            message_groups = await self.redis.xreadgroup(
                NOTIFY_WORKER_GROUP,
                self._name,
                streams={NOTIFY_WORKER_STREAM: '>'},
                block=100,
                count=1
            )
            for _, messages in message_groups:
                for _id, fn in messages:
                    try:
                        if 'message' in fn:
                            message = self.build_notify(fn.get('message'))
                            await message()
                            task = message
                        else:
                            encoded_task = fn.get('task')
                            task_id = fn.get('uid')
                            # Process the task
                            serialized_task = base64.b64decode(encoded_task)
                            task = cloudpickle.loads(serialized_task)
                            self.logger.info(
                                f':: TASK RECEIVED: {task} with id {task_id} at {int(time.time())}'
                            )
                            try:
                                result = await task()
                                self.logger.debug(
                                    f'Task Result {result!r}'
                                )
                                if isinstance(result, BaseException):
                                    raise result.__class__(str(result))
                                self.logger.info(
                                    f":: TASK {task}.{task_id} was executed at {int(time.time())}"
                                )
                            except Exception as e:
                                self.logger.error(
                                    f"Task {task}:{task_id} failed with error {e}"
                                )
                                raise
                        # If processing raises an exception, the next line won't be executed
                        await self.redis.xack(
                            NOTIFY_WORKER_STREAM,
                            NOTIFY_WORKER_GROUP,
                            _id
                        )
                        self.logger.info(
                            (
                                f":: TASK {task} was acknowledged by Worker {self._name} "
                                f"from {NOTIFY_WORKER_STREAM} at {int(time.time())}"
                            )

                        )
                    except Exception as e:
                        self.logger.error(
                            f"Error processing message: {e}"
                        )
            await asyncio.sleep(0.001)  # sleep a bit to prevent high CPU usage
        except ConnectionResetError:
            self.logger.error(
                "Connection was closed, trying to reconnect."
            )
            await asyncio.sleep(1)  # Wait for a bit before trying to reconnect
            raise
        except asyncio.CancelledError:
            raise

    async def start_stream(self):
        # Create the stream if it doesn't exist
        await self.ensure_group_exists()
        info = await self.redis.xinfo_groups(NOTIFY_WORKER_STREAM)
        self.logger.debug(f'Groups Info: {info}')
        # Clean up old messages before starting
        await self.cleanup_old_messages()

        if self._notify_empty_stream is True:
            # Start the empty stream checker task if enabled
            self.empty_stream_checker_task = asyncio.create_task(
                self.check_stream_empty()
            )
        self.logger.notice(
            f"Notify Service Started at {self.host}:{self.port} with Redis: {self.redis}"
        )

    async def start_subscription(self):
        """Starts PUB/SUB and a Redis Stream."""
        try:
            # Starts a Publish/Subcribe system:
            self.pubsub = self.redis.pubsub()
            await self.pubsub.subscribe(NOTIFY_CHANNEL)

            # Starts and prepare a Stream:
            await self.start_stream()

            # While Running
            while self._running:
                # Publish/Subscription Process:
                try:
                    await self.publish_subscribe()
                    # then, check the stream:
                    await self.check_stream()
                    # sleep a bit to prevent high CPU usage
                    await asyncio.sleep(0.001)
                except ConnectionResetError:
                    # Try to restart the subscription
                    await self.start_subscription()
                except ConnectionError:
                    break
                except asyncio.CancelledError:
                    break
                except KeyboardInterrupt:
                    break
                except Exception as exc:
                    # Handle other exceptions as necessary
                    print(exc, type(exc))
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

    async def close_redis(self):
        """Closes Redis Connection and PUB/SUB Subscription."""
        try:
            # Get a new pubsub object and unsubscribe from 'channel'
            await self.pubsub.unsubscribe(NOTIFY_CHANNEL)
        except RuntimeError as err:
            self.logger.exception(
                err, stack_info=True
            )
        # Closing the Stream:
        try:
            # remove the Empty Stream Checker:
            if self._notify_empty_stream is True:
                self.empty_stream_checker_task.cancel()
                await self.empty_stream_checker_task
            # and remove the stream:
            await self.redis.xgroup_delconsumer(
                NOTIFY_WORKER_STREAM,
                NOTIFY_WORKER_GROUP,
                self._name
            )
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self.logger.exception(
                exc, stack_info=True
            )
        try:
            await asyncio.wait_for(self.redis.close(), timeout=2.0)
        except asyncio.TimeoutError:
            self.logger.error(
                "Redis took too long to close."
            )
        try:
            await self.pool.disconnect(
                inuse_connections=True
            )
        except RuntimeError as err:
            self.logger.exception(
                err, stack_info=True
            )

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
            # closing redis:
            await self.close_redis()
        except KeyboardInterrupt:
            pass
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
            self.logger.error("Server Closing due timed out.")
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
                await self.queue.put(message, id=message.uid)
                result = f'Message {message!s} was Queued with id {message.uid}.'.encode('utf-8')
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
