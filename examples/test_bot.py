import asyncio
from aiohttp import web
from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings
from botbuilder.schema import Activity, ActivityTypes, Attachment

class SimpleBot:
    async def on_turn(self, turn_context):
        if turn_context.activity.value:
            # Handle the Adaptive Card input
            user_input = turn_context.activity.value.get("userMessage", "")
            print(f"Received message from user: {user_input}")
            await turn_context.send_activity(f"You said: {user_input}")
        else:
            # Send the Adaptive Card to the user
            card_attachment = self.create_adaptive_card_attachment()
            message = Activity(type=ActivityTypes.message)
            message.attachments = [card_attachment]
            await turn_context.send_activity(message)

    def create_adaptive_card_attachment(self) -> Attachment:
        card_content = {
            "type": "AdaptiveCard",
            "version": "1.0",
            "body": [
                {
                    "type": "TextBlock",
                    "text": "Enter your message:"
                },
                {
                    "type": "Input.Text",
                    "id": "userMessage",
                    "placeholder": "Type your message here...",
                    "isMultiline": True
                }
            ],
            "actions": [
                {
                    "type": "Action.Submit",
                    "title": "Send"
                }
            ]
        }
        return Attachment(
            content_type="application/vnd.microsoft.card.adaptive",
            content=card_content
        )

# Adapter settings
APP_ID = "09b01e47-6e19-4f7e-9f72-4683c5e0a83e"
APP_PASSWORD = "09b01e47-6e19-4f7e-9f72-4683c5e0a83e"
SETTINGS = BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD)
ADAPTER = BotFrameworkAdapter(SETTINGS)

BOT = SimpleBot()

async def messages(req):
    body = await req.json()
    activity = Activity().deserialize(body)
    auth_header = req.headers.get("Authorization", "")
    response = await ADAPTER.process_activity(activity, auth_header, BOT.on_turn)
    return web.Response(status=response.status)

app = web.Application()
app.router.add_post("/api/messages", messages)

if __name__ == "__main__":
    try:
        web.run_app(app, host="localhost", port=3978)
    except Exception as error:
        raise error
