import asyncio
from notify.models import TeamsWebhook, TeamsCard, TeamsChannel
from notify.providers.teams import Teams
from notify.conf import (
    MS_TEAMS_DEFAULT_TEAMS_ID,
    MS_TEAMS_DEFAULT_CHANNEL_ID,
    MS_TEAMS_DEFAULT_WEBHOOK
)

async def send_teams_webhook():
    tm = Teams()
    channel = TeamsWebhook(
        uri=MS_TEAMS_DEFAULT_WEBHOOK
    )
    msg = TeamsCard(text='🛑⚠️✅  Mensaje de PRUEBAS enviado a Navigator Teams', summary='Card Summary')
    #  add a section:
    msg.addSection(
        activityTitle='Test Activity Title',
        text='Potential text on Section'
    )
    async with tm as conn:
        result = await conn.send(
            recipient=channel,
            message=msg
        )
    print('RESULT > ', result)

async def send_teams_api():
    tm = Teams(as_user=True)
    channel = TeamsChannel(
        name='Navigator',
        team_id=MS_TEAMS_DEFAULT_TEAMS_ID,
        channel_id=MS_TEAMS_DEFAULT_CHANNEL_ID
    )
    msg = TeamsCard(text='✅  Test Message using Teams API', summary='Card Summary')
    #  add a section:
    section = msg.addSection(
        activityTitle='Test Activity Title',
        text='Potential text on Section'
    )
    section.addFacts(
        facts=[
            {
                "name": "Fact Name 1",
                "value": "Fact Value 1"
            },
            {
                "name": "Fact Name 2",
                "value": "Fact Value 2"
            }
        ]
    )
    async with tm as conn:
        result = await conn.send(
            recipient=channel,
            message=msg
        )
    print('RESULT > ', result)

async def send_teams_login():
    tm = Teams(as_user=True)
    channel = TeamsChannel(
        name='Navigator',
        team_id=MS_TEAMS_DEFAULT_TEAMS_ID,
        channel_id=MS_TEAMS_DEFAULT_CHANNEL_ID
    )
    msg = TeamsCard(title='✅  Login Form using Teams API')
    msg.addAction(
        type='Action.Submit', title="Login into NAV", id="LoginVal"
    )
    msg.addInput(
        id="UserVal", label='Username', is_required=True, errorMessage="Username is required"
    )
    msg.addInput(
        id="PassVal",
        label='Password',
        is_required=True,
        errorMessage="Password is required",
        style="Password"
    )
    async with tm as conn:
        result = await conn.send(
            recipient=channel,
            message=msg
        )
    print('RESULT > ', result)

if __name__ == "__main__":
    # asyncio.run(send_teams_webhook())
    asyncio.run(send_teams_api())
    # asyncio.run(send_teams_login())
