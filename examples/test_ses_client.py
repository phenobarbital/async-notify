# Example usage
import asyncio
from navconfig import config
from notify.server import NotifyClient
from notify.conf import NOTIFY_CHANNEL, NOTIFY_WORKER_STREAM

async def main():
    credentials = {
        "aws_access_key_id": config.get('AWS_ACCESS_KEY_ID'),
        "aws_secret_access_key": config.get('AWS_SECRET_ACCESS_KEY'),
        "aws_region_name": config.get('AWS_REGION_NAME'),
        "sender_email": "navigatoralerts@trocglobal.com"
    }
    # Sample message
    msg = {
        "provider": "ses",
        **credentials,
        "recipient": [
            {
                "name": "Jesus Lara",
                "account": {
                    "address": "jesuslarag@gmail.com",
                    "number": "+34692817379"
                }
            }
        ],
        "message": 'Congratulations!',
        "template": 'email_applied.html'
    }

    # Create a NotifyClient instance
    async with NotifyClient() as client:
        # Stream but using Wrapper:
        await client.stream(msg, stream=NOTIFY_WORKER_STREAM, use_wrapper=True)

# Run the example
if __name__ == "__main__":
    asyncio.run(main())
