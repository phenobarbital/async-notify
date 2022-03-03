from notify.models import Actor
from notify.utils import Msg
from notify import Notify

from notify.providers.gmail import Gmail
import asyncio

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
recipients = [ Actor(**user), Actor(**user2) ]
jesus = Actor(**user)

Msg('=== GMAIL ===')

d = Gmail()

def status_sent(recipient, message, result, task):
    print(f'Notification with status {result!s} to {recipient.account!s}')

d.sent = status_sent

result = loop.run_until_complete(
    d.send(
        recipient=recipients,
        subject='Epale, vente a jugar bolas criollas!',
        event_name='Partido de bolas Criollas',
        event_address='Bolodromo Caucagua',
        template='email_applied.html'
    )
)
print(result)
d.close() # close is not async on gmail.

Msg('=== GMAIL in a Context Method ===')

mail = Gmail()

async def send_email():
    async with mail as m:
        await m.send(
            recipient=recipients,
            subject='Epale, vente a jugar bolas criollas!',
            event_name='Partido de bolas Criollas',
            event_address='Bolodromo Caucagua',
            template='email_applied.html'
        )
        
asyncio.run(send_email())