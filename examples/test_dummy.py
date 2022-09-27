import asyncio
from notify import Notify
from notify.utils import Msg
from notify.models import Actor
from notify.providers.dummy import Dummy

# first: create recipients:
user = {
    "name": "Jesus Lara",
    "account": [
        {
        "provider": "twilio",
        "phone": "+343317871"
        },
        {
        "provider": "email",
        "address": "jesuslara@jesuslara.com"
        },
        {
        "provider": "jabber",
        "address": "jesuslara@jesuslara.com"
        }
    ]
}
user2 = {
    "name": "Jesus Lara",
    "account": {
        "provider": "twitter",
        "address": "jesuslara@jesuslara.com"
    }
}
user3 = {
    "name": "Javier León",
    "account": {
        "address": "jelitox@gmail.com"
    }
}
user4 = {
    "name": "Guillermo Amador",
    "account": {
        "provider": "email",
        "address": "guillermo@gmail.com"
    }
}
user5 = {
    "name": "Steven Smith",
    "account": {
        "provider": "o365",
        "address": "guillermo@outlook.com"
    }
}
recipients = [ Actor(**user), Actor(**user2), Actor(**user3), Actor(**user4), Actor(**user5) ]
jesus = Actor(**user)

Msg('=== DUMMY Sample. ===')

dummy = Dummy() # we can also create directly.
d = Notify('dummy')
print('Module: ', d)

def status_sent(recipient, message, result, **kwargs):
    Msg(f':: Notification with status {bool(result)} for {recipient.account!s}', level='DEBUG')
d.sent = status_sent

asyncio.run(
    d.send(
        recipient=recipients,
        message='Congratulations!',
        template='template_hello.txt'
    )
)
