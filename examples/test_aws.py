import asyncio
from notify.providers.aws import Aws
from notify.models import Actor
from notify.utils import Msg

Msg('=== Send EMAIL with Amazon AWS === ')

user = {
    "name": "Jesus Lara",
    "account": {
        "address": "jesuslarag@gmail.com",
        "phone": "+34692817379"
    }
}
recipients = [Actor(**user)]

async def send_email():
    mail = Aws()
    async with mail as m:
        await m.send(
            recipient=recipients,
            subject='Epale, vente a jugar bolas criollas!',
            event_name='Partido de bolas Criollas',
            event_address='Bolodromo Caucagua',
            template='email_applied.html'
        )

asyncio.run(send_email())
