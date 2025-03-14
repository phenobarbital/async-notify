import asyncio
import random
import uuid
import json
from redis import Redis
from notify.conf import (
    NOTIFY_CHANNEL,
    NOTIFY_WORKER_STREAM,
)
from notify.server import NotifyWrapper


async def tcp_send(message, host='localhost', port=8991):
    # Open a TCP connection to the server
    try:
        _, writer = await asyncio.open_connection(host, port)

        # Encode the message as bytes and send it
        writer.write(message.encode())
        await writer.drain()

        # Close the connection
        writer.close()
        await writer.wait_closed()
        print(f"Message sent to TCP server: {message}")
    except Exception as e:
        print(
            f"Failed to send message to TCP server: {e}"
        )

def redis_publish(message, channel=NOTIFY_CHANNEL):
    # Connect to Redis
    redis = Redis()

    # Publish the message to the channel
    redis.publish(channel, message)

def redis_stream_publish(message, stream=NOTIFY_WORKER_STREAM):
    """Publish a message to a Redis Stream."""
    try:
        # Connect to Redis
        redis = Redis(
            host="localhost",
            port=6379,
            db=5
        )

        uid = uuid.uuid1(
            node=random.getrandbits(48) | 0x010000000000
        )

        msg = {
            "uid": str(uid),
            "task": {"message": message}
        }

        # Publish the message to the Redis stream
        redis.xadd(stream, {"message": message})
        print(
            f"Message published to stream {stream}: {message}"
        )
    except Exception as e:
        print(
            f"Failed to publish message to Redis stream: {e}"
        )

if __name__ == '__main__':
    # Define a message
    msg = {
        "provider": "dummy",
        "recipient": [
            {
                "name": "Steven Smith",
                "account": {
                    "provider": "o365",
                    "address": "guillermo@outlook.com"
                }
            },
            {
                "name": "Javier León",
                "account": {
                    "address": "jelitox@gmail.com"
                }
            }
        ],
        "message": 'Congratulations!',
        "template": 'template_hello.txt'
    }
    data = json.dumps(msg)

    # Start the asyncio event loop
    loop = asyncio.get_event_loop()

    try:
        for _ in range(0, 5):
            # Send the message via TCP
            loop.run_until_complete(tcp_send(data))
            # Publish the same message to Redis
            redis_publish(data, channel=NOTIFY_CHANNEL)
            # Publish the message to the Redis stream
            redis_stream_publish(data, stream=NOTIFY_WORKER_STREAM)
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        loop.close()
