import asyncio
from notify.providers.office365 import Office365
from notify.models import Actor
from notify import Notify

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

user = {
    "name": "Jesus Lara",
    "account": {
        "address": "jesuslarag@gmail.com",
        "phone": "+34692817379"
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
e = Notify('office365')
result = loop.run_until_complete(
    e.send(
        recipient=recipients,
        subject='Epale, vente a jugar bolas criollas!',
        event_name='Partido de bolas Criollas',
        event_address='Bolodromo Caucagua',
        template='email_applied.html'
    )
)
print('THIS > ', result)
loop.run_until_complete(e.close())
