import asyncio
from notify.utils import Msg
from notify.models import Actor, Channel
from notify.providers.slack import Slack
from notify.providers.slack.settings import SLACK_DEFAULT_CHANNEL


channel = Channel(channel_id=SLACK_DEFAULT_CHANNEL, channel_name='navigator-tests')

Msg('==== SLACK to CHANNEL === ')

async def send_slack():
    slack = Slack()
    async with slack as conn:
        await conn.send(
            recipient=channel,
            message='🛑⚠️✅ Mensaje de PRUEBAS enviado a Navigator Daily-Stand Up.'
        )

asyncio.run(send_slack())

Msg('==== SLACK to User === ')


user = {
    "name": "Jesus Lara",
    "account": {
        "provider": "slack",
        "userid": "U82HJF9F1"
    }
}
jesus = Actor(**user)
async def send_to_user():
    slack = Slack()
    async with slack as conn:
        await conn.send(
            recipient=jesus,
            message='🛑⚠️✅ Mensaje de PRUEBAS enviado en Privado.'
        )
asyncio.run(send_to_user())
