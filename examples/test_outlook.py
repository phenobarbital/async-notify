import asyncio
from navconfig import BASE_DIR
from notify.providers.outlook import Outlook
from notify.models import Actor

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
    mail = Outlook(use_credentials=True)
    ## add an Attachment
    f = BASE_DIR.joinpath('INSTALL')
    await mail.add_attachment(f)
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
