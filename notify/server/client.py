from typing import Any
import asyncio
import base64
import json
import cloudpickle
from redis import asyncio as aioredis
from navconfig.logging import logging
from notify.server import NotifyWrapper


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
        self.redis_url = redis_url
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_db = redis_db
        self.tcp_host = tcp_host
        self.tcp_port = tcp_port
        self.redis = None
        self.logger = logging.getLogger('Notify.Client')

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
