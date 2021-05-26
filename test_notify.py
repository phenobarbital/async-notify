#from notify import Notify
from pathlib import Path, PurePath
from notify.models import Actor, Chat, Account, Message, BlockMessage, MailMessage
from notify import Notify

from notify.providers.dummy import Dummy
import asyncio

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
#
#
# print('=== DUMMY ===')
# #d = Dummy()
# d = Notify('dummy')
#
# def status_sent(recipient, message, result, task):
#     print(f'Notification with status {result!s} to {recipient.account!s}')
# d.sent = status_sent
#
# asyncio.run(d.send(
#     recipient=recipients,
#     message='Congratulations!',
#     template='template_hello.txt'
# ))
#
# print('=== EMAIL ===')
# account = {
#     "host": 'smtp.sendgrid.net',
#     "port": 587,
#     "password": 'JFDHVtgH4cL3Jl',
#     "username": 'alert@mobileinsight.com'
# }
#
# #from notify.providers.gmail import Gmail
# e = Notify('email', **account)
#
# #e = Notify('gmail')
# result = asyncio.run(e.send(
#     recipient=jesus,
#     subject='Epale, vente a jugar bolas criollas!',
#     event_name='Partido de bolas Criollas',
#     event_address='Bolodromo Caucagua',
#     template='email_applied.html'
# ))
# print(result)


# print('=== SMS ===')
#
# from notify.providers.twilio import Twilio
#
#
# msg = Twilio()
# asyncio.run(msg.send(
#     recipient=jesus,
#     message='Test Message From Navigator Notify'
# ))
#
# print('==== TELEGRAM === ')
# from notify.providers.telegram import Telegram
#
# chat = Chat(**{"chat_id": '-1001277497822'})
# t = Telegram()
# asyncio.run(t.send(
#     recipient=chat,
#     message='🛑⚠️✅   Mensaje a Navigator Telegram',
#     disable_notification=True
# ))

#
# email = {
#     "text": 'Test Message From Navigator Notify',
#     "html": html
# }
#
# account = {
#     "host": 'smtp.sendgrid.net',
#     "port": 587,
#     "password": 'JFDHVtgH4cL3Jl',
#     "username": 'alert@mobileinsight.com'
# }
# msg = n.provider('email', **account)
# msg.send(
#     to='jesuslarag@gmail.com',
#     subject='Test: Email notification from Navigator',
#     message=email
# )

# m = Notify('twilio', level='DEBUG')
# m.send('Otro mensaje de prueba')


t = Notify('telegram')
asyncio.run(
    t.send('🛑⚠️✅   Mensaje de Prueba', disable_notification=True)
)

image = PurePath().joinpath('docs/old-computer.jpg')
asyncio.run(
 t.send_photo(photo=image, caption='🛑 Pie de imagen')
)

document = PurePath().joinpath('/home/ubuntu/symbits/dataintegrator.zip')
asyncio.run(
 t.send_document(document=document, caption='⚠️ Pie de archivo', disable_notification=True)
)
