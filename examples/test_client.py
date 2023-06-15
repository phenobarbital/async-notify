import asyncio
import json
from redis import Redis
from notify.conf import NOTIFY_CHANNEL

async def tcp_send(message, host='localhost', port=8991):
    # Open a TCP connection to the server
    _, writer = await asyncio.open_connection(host, port)

    # Encode the message as bytes and send it
    writer.write(message.encode())
    await writer.drain()

    # Close the connection
    writer.close()
    await writer.wait_closed()

def redis_publish(message, channel=NOTIFY_CHANNEL):
    # Connect to Redis
    redis = Redis()

    # Publish the message to the channel
    redis.publish(channel, message)

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
        for _ in range(0, 500):
            # Send the message via TCP
            loop.run_until_complete(tcp_send(data))
            # Publish the same message to Redis
            redis_publish(data, channel=NOTIFY_CHANNEL)
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        loop.close()
