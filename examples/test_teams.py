import asyncio
from notify.models import TeamsCard, TeamsWebhook
from notify.providers.teams import Teams


msg = TeamsCard(text='🛑⚠️✅  Mensaje de PRUEBAS enviado a Navigator Teams')

channel = TeamsWebhook(
    uri='https://symbits.webhook.office.com/webhookb2/7a795c62-c523-4b6c-aafe-fe7cb7b03d7f@af176793-abc4-423e-8fab-dfc4e2bf8b9d/IncomingWebhook/2464692884f44012b6c8e0f6e73a702e/4e2aa0ea-56b8-49fe-85cf-05e97d479ba6'
)


async def send_teams():
    tm = Teams()
    async with tm as conn:
        await conn.send(
            recipient=channel,
            message=msg
        )

if __name__ == "__main__":
    asyncio.run(send_teams())
