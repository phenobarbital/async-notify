import asyncio
from notify.providers.smtp import SMTP
from notify.models import Actor
from notify.utils import Msg

user = {
    "name": "Jesus Lara",
    "account": {
        "address": "jesuslarag@gmail.com",
        "number": "+34692817379"
    }
}
user2 = {
    "name": "Jesus Lara",
    "account": {
        "provider": "email",
        "address": "jesuslara@devel.com.ve"
    }
}
recipients = [Actor(**user), Actor(**user2)]
jesus = Actor(**user)

Msg('=== Test SMTP with Default Settings === ')
async def send_email():
    mail = SMTP()
    async with mail as m:
        await m.send(
            recipient=recipients,
            subject='Epale, vente a jugar bolas criollas!',
            event_name='Partido de bolas Criollas',
            event_address='Bolodromo Caucagua',
            template='email_applied.html'
        )


if __name__ == '__main__':
    asyncio.run(send_email())
