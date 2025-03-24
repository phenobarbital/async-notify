import asyncio
from notify.providers.dialpad import Dialpad
from notify.models import Actor
from notify.utils import Msg

user1 = {
    "name": "Jesus Lara",
    "account": {
        "address": "jesuslarag@gmail.com",
        "number": "+34692817379"
    }
}

user2 = {
    "name": "William Cabrera",
    "account": {
        "address": "cabrerawilliam@gmail.com",
        "number": "+34612292970"
    }
}

recipients = [Actor(**user1), Actor(**user2)]

async def send_sms():
    sms = Dialpad()
    async with sms as s:
        await s.send(
            message='Test SMS',
            recipient=recipients,
            template='template_hello.txt'
        )

asyncio.run(send_sms())