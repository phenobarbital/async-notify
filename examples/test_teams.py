import asyncio
from notify.models import TeamsCard, TeamsChannel
from notify.providers.teams import Teams


msg = TeamsCard(text='🛑⚠️✅  Mensaje de PRUEBAS enviado a Navigator Teams')

channel = TeamsChannel(uri='https://teams.microsoft.com/l/channel/19%3ad5f1ab3372b541a980f4c79c1668b321%40thread.tacv2/Navigator?groupId=7a795c62-c523-4b6c-aafe-fe7cb7b03d7f&tenantId=af176793-abc4-423e-8fab-dfc4e2bf8b9d')


async def send_teams():
    tm = Teams()
    async with tm as conn:
        await conn.send(
            recipient=channel,
            message=msg
        )

if __name__ == "__main__":
    asyncio.run(send_teams())
