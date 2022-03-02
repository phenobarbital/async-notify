from notify import Notify
from notify.utils import Msg
from notify.models import Actor
from notify.providers.dummy import Dummy
import asyncio

# first: create recipients:
user = {
    "name": "Jesus Lara",
    "account": {
        "address": "jesuslara@gmail.com",
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
user3 = {
    "name": "Javier León",
    "account": {
        "address": "jel1284@gmail.com"
    }
}
recipients = [ Actor(**user), Actor(**user2), Actor(**user3) ]
jesus = Actor(**user)


Msg('=== DUMMY Sample. ===')

dummy = Dummy() # we can also create directly.
d = Notify('dummy')

def status_sent(recipient, message, result, task):
    print(f'Notification with status {result!s} to {recipient.account!s}')
d.sent = status_sent

asyncio.run(
    d.send(
        recipient=recipients,
        message='Congratulations!',
        template='template_hello.txt'
    )
)