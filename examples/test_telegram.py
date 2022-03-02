
from pathlib import Path, PurePath
from notify.models import Actor, Chat, Account, Message, BlockMessage, MailMessage
from notify.utils import Msg

from notify import Notify
from notify.providers.telegram import Telegram
import asyncio


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

Msg('==== TELEGRAM === ')

chat = Chat(**{"chat_id": '-1001277497822'})

async def send_telegram():
    tm = Telegram()
    async with tm as conn:
        await conn.send(
            recipient=chat,
            message='🛑⚠️✅   Mensaje de PRUEBAS enviado a Navigator Telegram',
            disable_notification=False
        )
        
asyncio.run(send_telegram())

async def test_telegram():
    telegram = Notify('telegram')
    async with telegram as t:
        await t.send('🛑⚠️✅ Otro Mensaje de Prueba', disable_notification=True)
        image = PurePath().joinpath('docs/old-computer.jpg')
        await t.send_photo(photo=image, caption='🛑 Pie de imagen')
        document = PurePath().joinpath('docs/requirements-dev.txt')
        await t.send_document(document=document, caption='⚠️ Documento de Ejemplo', disable_notification=True)

asyncio.run(test_telegram())
