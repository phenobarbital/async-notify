from typing import Any
import asyncio
import base64
import json
import cloudpickle
from redis import asyncio as aioredis
from navconfig.logging import logging
from qw.discovery import get_client_discovery
from qw.conf import WORKER_LIST
from .server import NotifyWrapper
from ..conf import (
    NOTIFY_REDIS,
    NOTIFY_DEFAULT_PORT,
    NOTIFY_USE_DISCOVERY
)


class NotifyClient:
    """NotifyClient handles sending messages
    via TCP, Redis PUB/SUB, and Redis Streams.

    Attributes:

    """

    def __init__(
        self,
        redis_url: str = None,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 5,
        tcp_host: str = 'localhost',
        tcp_port: str = 8991
    ):
        """
        Initialize NotifyClient.

        Args:
            redis_url: The URL to connect to Redis (for aioredis from_url).
            redis_host: Redis host (if URL is not provided).
            redis_port: Redis port (if URL is not provided).
            redis_db: Redis Database (if URL is not provided).
            tcp_host: The host for TCP connections.
            tcp_port: The port for TCP connections.
        """
        self.logger = logging.getLogger('Notify.Client')
        if not redis_url:
            self.redis_url = NOTIFY_REDIS
        else:
            self.redis_url = redis_url
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_db = redis_db
        # configure worker:
        if NOTIFY_USE_DISCOVERY is True:
            # get worker list from discovery:
            _, worker_list = get_client_discovery()
            if not worker_list:
                self.logger.warning(
                    'EMPTY WORKER LIST: Trying to connect to a default Worker'
                )
                # try to connect with the default worker
                self.tcp_host = WORKER_LIST[0][0]
                self.tcp_port = WORKER_LIST[0][1]
            else:
                workers = [tuple(a) for a in worker_list]
                self.tcp_host = workers[0][0]
                self.tcp_port = workers[0][1]
        elif tcp_host and tcp_port:
            # use manually
            self.tcp_host = tcp_host
            self.tcp_port = tcp_port
        else:
            self.tcp_host = WORKER_LIST[0][0]
            self.tcp_port = NOTIFY_DEFAULT_PORT
        self.redis = None

    def register_pickle_module(self, module: Any):
        cloudpickle.register_pickle_by_value(module)

    async def connect(self):
        """Connect to Redis using aioredis."""
        if self.redis_url:
            self.redis = aioredis.from_url(
                self.redis_url,
                decode_responses=True
            )
        else:
            self.redis = aioredis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=self.redis_db,
                decode_responses=True
            )
        self.logger.debug(
            f"Connected to Redis at {self.redis_url or f'{self.redis_host}:{self.redis_port}'}"
        )

    async def publish(self, message: dict, channel: str):
        """Publish a message to Redis PUB/SUB channel."""
        if not self.redis:
            await self.connect_redis()

        data = json.dumps(message)
        await self.redis.publish(channel, data)
        self.logger.debug(f"Message published to channel {channel}: {data}")

    async def stream(self, message: dict, stream: str, use_wrapper: bool = False):
        """Publish a message to a Redis Stream."""
        if not self.redis:
            await self.connect_redis()

        # Create the Wrapper at the Client Side:
        if use_wrapper is True:
            fn = NotifyWrapper(**message)
            serialized_task = cloudpickle.dumps(fn)
            encoded_task = base64.b64encode(serialized_task).decode('utf-8')
            msg = {
                "uid": fn.uid,
                "task": encoded_task
            }
        else:
            data = json.dumps(message)
            msg = {"message": data}
        await self.redis.xadd(stream, msg)
        self.logger.debug(
            f"Message published to stream {stream}: {message}"
        )

    async def send(self, message: dict):
        """Send a message via a TCP connection."""
        try:
            _, writer = await asyncio.open_connection(self.tcp_host, self.tcp_port)

            data = json.dumps(message)
            writer.write(data.encode())
            await writer.drain()

            self.logger.debug(f"Message sent to TCP server: {data}")

            writer.close()
            await writer.wait_closed()
        except Exception as e:
            print(f"Failed to send message via TCP: {e}")

    async def close(self):
        """Close Redis connection."""
        if self.redis:
            await self.redis.close()
            print("Redis connection closed.")

    async def __aenter__(self):
        """Enter the async context by opening the Redis connection."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        """Exit the async context by closing the Redis connection."""
        await self.close()
