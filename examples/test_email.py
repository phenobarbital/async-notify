import asyncio
from navconfig import config
from notify.providers.email import Email
from notify.models import Actor
from notify.utils import Msg
from notify import Notify


loop = asyncio.get_event_loop()
asyncio.set_event_loop(loop)

stmp_host_user = config.get('stmp_host_user')
stmp_host_password = config.get('stmp_host_password')
stmp_host = config.get('stmp_host')
stmp_port = config.get('stmp_port')


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


Msg('=== Test EMAIL with Another Account === ')
account = {
    "hostname": stmp_host,
    "port": stmp_port,
    "password": stmp_host_password,
    "username": stmp_host_user
}

# e = Notify('email', **account)
# result = loop.run_until_complete(
#     e.send(
#         recipient=recipients,
#         subject='Epale, vente a jugar bolas criollas!',
#         event_name='Partido de bolas Criollas',
#         event_address='Bolodromo Caucagua',
#         template='email_applied.html'
#     )
# )
# print(result)
# loop.run_until_complete(e.close())

Msg('=== Test EMAIL with Default Settings === ')
async def send_email():
    mail = Email()
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
