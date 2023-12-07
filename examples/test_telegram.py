import asyncio
from pathlib import Path
from navconfig import BASE_DIR
from notify.models import Actor, Chat
from notify.utils import Msg
from notify import Notify
from notify.providers.telegram import Telegram


user = {
    "name": "Jesus Lara",
    "account": {
        "address": "jesuslara@gmail.com",
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
user3 = {
    "name": "Javier León",
    "account": {
        "address": "jel1284@gmail.com"
    }
}
recipients = [Actor(**user), Actor(**user2), Actor(**user3)]
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
    async with telegram as t:  # pylint: disable=not-async-context-manager
        await t.send(
            recipient=chat,
            message='🛑⚠️✅ Otro Mensaje de Prueba',
            disable_notification=True
        )
        image = Path().joinpath('docs/old-computer.jpg')
        await t.send_photo(photo=image, caption='🛑 Pie de imagen')
        document = Path().joinpath('docs/requirements-dev.txt')
        await t.send_document(
            document=document,
            caption='⚠️ Documento de Ejemplo',
            disable_notification=True
        )
        ### an Sticker:
        sticker = {"set": "RadioRochela", "emoji": '💋'}
        # sticker = {"set": "PokemonGo", "emoji": ':unamused_face:'}
        await t.send_sticker(sticker=sticker, disable_notification=True)
        ## Video:
        video = BASE_DIR.joinpath(
            'docs/(72) Rick Astley - Never Gonna Give You Up (video oficial) -1.webm'
        )
        await t.send_video(
            video=video,
            caption='✅ Never Gonna Give You Up!',
            supports_streaming=True,
            disable_notification=True
        )
        ## Audio:
        dialup = BASE_DIR.joinpath('docs/Dialup.mp3')
        await t.send_audio(
            audio=dialup,
            caption='✅ Dial-Up',
            disable_notification=True
        )

asyncio.run(test_telegram())
