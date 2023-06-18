import asyncio
from notify.providers.office365 import Office365
from notify.models import Actor
from notify import Notify

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


async def send_mail():
    recipients = [Actor(**user), Actor(**user2)]
    mail = Notify('office365', use_credentials=True)
    async with mail as m:
        result = await m.send(
            recipient=recipients,
            subject='Epale, vente a jugar bolas criollas!',
            event_name='Partido de bolas Criollas',
            event_address='Bolodromo Caucagua',
            template='email_applied.html'
        )
        print('THIS > ', result)

if __name__ == '__main__':
    asyncio.run(send_mail())
