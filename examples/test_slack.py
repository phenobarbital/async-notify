import asyncio
from notify.utils import Msg
from notify.models import Actor, Channel
from notify.providers.slack import Slack
from notify.conf import SLACK_DEFAULT_CHANNEL


# channel = Channel(channel_id=SLACK_DEFAULT_CHANNEL, channel_name='navigator-tests')
channel = Channel(
    channel_id='C02GZ0LCMLN', channel_name='navigator-development'
)
Msg('==== SLACK to CHANNEL === ')

async def send_slack():
    slack = Slack()
    async with slack as conn:
        await conn.send(
            recipient=channel,
            message='🛑⚠️✅ Mensaje de PRUEBAS enviado a Navigator Development.'
        )

asyncio.run(send_slack())

Msg('==== SLACK to User === ')


user = {
    "name": "Javier León",
    "account": {
        "provider": "slack",
        "userid": "U01FF7KSG6P"
    }
}
jelitox = Actor(**user)
async def send_to_user():
    slack = Slack()
    async with slack as conn:
        await conn.send(
            recipient=jelitox,
            message='🛑⚠️✅ Mensaje a Jelitox enviado en Privado.'
        )
asyncio.run(send_to_user())
