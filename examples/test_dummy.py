import time
import asyncio
from notify import Notify
from notify.utils import Msg
from notify.models import Actor
from notify.providers.dummy import Dummy


started_at = time.monotonic()

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
user6 = {
    "name": "Eduardo Galeano",
    "account": {
        "provider": "o365",
        "address": "eduardo@outlook.com"
    }
}
recipients = [Actor(**user), Actor(**user2), Actor(**user3), Actor(**user4), Actor(**user5), Actor(**user6)]
jesus = Actor(**user)

Msg('=== DUMMY Sample. ===')

dummy = Dummy()  # we can also create directly.
d = Notify('dummy')
print('Module: ', d)

def status_sent(recipient, message, result, **kwargs):
    print('DEV> ', recipient, message, result, kwargs)
    Msg(
        f':: Notification with status {bool(result)} for {recipient.account!s}', level='DEBUG'
    )
d.sent = status_sent

results = asyncio.run(
    d.send(
        recipient=recipients,
        message='Congratulations!',
        template='template_hello.txt'
    )
)

print('RESULTS : > ', results)
total_slept = time.monotonic() - started_at
print(f"System ended: {total_slept}")
