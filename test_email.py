#from notify import Notify
from pathlib import Path, PurePath
from notify.models import Actor, Chat, Account, Message, BlockMessage, MailMessage
from notify import Notify

from notify.providers.dummy import Dummy
import asyncio

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

## Add two more providers: Twitter and Whatsapp via Twilio

# f = open(Path(__file__).parent.joinpath('sample_minified.html'), 'r')
# html = f.read()
#
# #TODO: working with Message Blocks and Models
# msg = Message(**{
#     "body": 'Test Message From Navigator Notify',
#     "content": html
# })

user = {
    "name": "Jesus Lara",
    "account": {
        "address": "jesuslara@gmail.com",
        "phone": "+34692817379"
    }
}
recipients = [ Actor(**user) ]
jesus = Actor(**user)


print('=== DUMMY ===')
#d = Dummy()
d = Notify('dummy')

def status_sent(recipient, message, result, task):
    print(f'Notification with status {result!s} to {recipient.account!s}')

d.sent = status_sent

asyncio.run(d.send(
    recipient=recipients,
    message='Congratulations!',
    template='template_hello.txt'
))

print('=== EMAIL ===')

account = {
    "hostname": 'smtp.sendgrid.net',
    "port": 587,
    "password": 'JFDHVtgH4cL3Jl',
    "username": 'alert@mobileinsight.com'
}


# account = {
#     "hostname": 'smtp.gmail.com',
#     "port": 587,
#     "password": 'xcagaqxayuxtibsx',
#     "username": 'jesuslarag@gmail.com'
# }

#from notify.providers.gmail import Gmail
e = Notify('email', loop=loop, **account)
loop.run_until_complete(e.connect())
print('IS CONNECTED: ', e.is_connected())
# #e = Notify('gmail')
result = loop.run_until_complete(e.send(
    recipient=jesus,
    subject='Epale, vente a jugar bolas criollas!',
    event_name='Partido de bolas Criollas',
    event_address='Bolodromo Caucagua',
    template='email_applied.html'
))
print(result)
loop.run_until_complete(e.close())
