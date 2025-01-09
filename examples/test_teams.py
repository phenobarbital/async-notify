import asyncio
from notify.models import Actor, TeamsWebhook, TeamsCard, TeamsChannel, TeamsChat
from notify.providers.teams import Teams
from notify.conf import (
    MS_TEAMS_DEFAULT_TEAMS_ID,
    MS_TEAMS_DEFAULT_CHANNEL_ID,
    MS_TEAMS_DEFAULT_WEBHOOK
)

async def send_teams_webhook():
    tm = Teams()
    channel = TeamsWebhook(
        # uri=MS_TEAMS_DEFAULT_WEBHOOK
        uri="https://symbits.webhook.office.com/webhookb2/7a795c62-c523-4b6c-aafe-fe7cb7b03d7f@af176793-abc4-423e-8fab-dfc4e2bf8b9d/IncomingWebhook/b053af82707e47d58bb9e37f55fc2b01/4e2aa0ea-56b8-49fe-85cf-05e97d479ba6"
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
    msg = TeamsCard(
        text='✅  Test Message using Teams API',
        summary='Card Summary'
    )
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

async def send_message_chat():
    chat = TeamsChat(
        name='Test_Chat',
        chat_id='19:6e39d89de86d4dc7b60550d9c2e464ca@thread.v2'
    )
    tm = Teams(as_user=True)
    msg = TeamsCard(text='🛑⚠️✅  Mensaje de PRUEBAS enviado a Navigator Teams', summary='Card Summary')
    #  add a section:
    msg.addSection(
        activityTitle='Test Activity Title',
        text='Potential text on Section'
    )
    async with tm as conn:
        result = await conn.send(
            recipient=chat,
            message=msg
        )
    print('RESULT > ', result)

async def send_direct_message():
    user = {
        "name": "Jesus Lara",
        "account": {
            "address": "jlara@trocglobal.com"
        }
    }
    try:
        recipient = Actor(**user)
    except Exception as e:
        print(f"Error creating recipient: {e.payload}")
        return
    tm = Teams(as_user=True)
    msg = TeamsCard(
        text='🛑⚠️✅  Mensaje de PRUEBAS enviado a Navigator Teams',
        summary='Card Summary'
    )
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
    msg.addInput(
        id="UserVal", label='Username'
    )
    msg.addInput(
        id="PassVal",
        label='Password',
        style="Password"
    )
    async with tm as conn:
        result = await conn.send(
            recipient=recipient,
            message=msg
        )
    print('RESULT > ', result)

if __name__ == "__main__":
    # asyncio.run(send_teams_webhook())
    asyncio.run(send_teams_api())
    # asyncio.run(send_teams_login())
    # asyncio.run(send_message_chat())
    # asyncio.run(send_direct_message())
