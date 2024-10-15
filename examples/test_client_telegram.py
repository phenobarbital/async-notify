# Example usage
import asyncio
from navconfig import config
from notify.server import NotifyClient
from notify.conf import NOTIFY_CHANNEL, NOTIFY_WORKER_STREAM

async def main():
    # Sample Telegram message
    msg = {
        "provider": "telegram",
        "recipient": [
            {
                "chat_id": config.get('TELEGRAM_CHAT_ID'),
                "chat_name": "Navigator (Nuevo Production)"
            }
        ],
        "message": '🛑⚠️✅   Mensaje de PRUEBAS With Notify Service!',
        "disable_notification": True
    }

    # Create a NotifyClient instance
    async with NotifyClient(
        redis_url="redis://localhost:6379/5",
        tcp_host="localhost",
        tcp_port=8991
    ) as client:
        # Publish to Redis PUB/SUB
        # await client.publish(msg, channel=NOTIFY_CHANNEL)

        # Stream into Redis stream
        # await client.stream(msg, stream=NOTIFY_WORKER_STREAM)

        # Stream but using Wrapper:
        await client.stream(msg, stream=NOTIFY_WORKER_STREAM, use_wrapper=True)

        # Send message via TCP
        # await client.send(msg)

# Run the example
if __name__ == "__main__":
    asyncio.run(main())
