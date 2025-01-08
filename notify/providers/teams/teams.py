from typing import Dict, Optional, Union, Any
import json
import uuid
import base64
import aiohttp
import msal
from azure.identity.aio import (
    ClientSecretCredential
)
from azure.identity import UsernamePasswordCredential
from msgraph import GraphServiceClient
from msgraph.generated.models.chat import Chat
from msgraph.generated.models.chat_type import ChatType
from msgraph.generated.models.chat_message import ChatMessage
from msgraph.generated.models.item_body import ItemBody
from msgraph.generated.models.body_type import BodyType
from msgraph.generated.models.chat_message_attachment import ChatMessageAttachment
from msgraph.generated.models.chat_message_hosted_content import ChatMessageHostedContent
from msgraph.generated.models.aad_user_conversation_member import AadUserConversationMember
from msgraph.generated.chats.chats_request_builder import ChatsRequestBuilder
from kiota_abstractions.base_request_configuration import RequestConfiguration
from navconfig.logging import logging
from notify.models import (
    Actor,
    TeamsWebhook,
    TeamsChannel,
    TeamsChat,
    TeamsCard
)
from notify.providers.base import ProviderIM, ProviderType
from notify.exceptions import NotifyException
from notify.conf import (
    # MS Teams information:
    MS_TEAMS_TENANT_ID,
    MS_TEAMS_CLIENT_ID,
    MS_TEAMS_CLIENT_SECRET,
    MS_TEAMS_DEFAULT_TEAMS_ID,
    MS_TEAMS_DEFAULT_CHANNEL_ID,
    MS_TEAMS_DEFAULT_WEBHOOK,
    O365_USER,
    O365_PASSWORD
)
from notify.exceptions import MessageError

# disable MSAL debug:
logging.getLogger('msal').setLevel(logging.INFO)
logging.getLogger('httpcore').setLevel(logging.INFO)
logging.getLogger('azure').setLevel(logging.WARNING)
logging.getLogger('hpack').setLevel(logging.INFO)
# disable aiohttp debug:
logging.getLogger('aiohttp').setLevel(logging.INFO)


class Teams(ProviderIM):
    """
    Teams.

    Send messages to a channel using Teams.
    """
    provider = "teams"
    provider_type = ProviderType.IM
    blocking: str = 'asyncio'

    def __init__(self, *args, **kwargs):
        self.as_user: bool = kwargs.pop('as_user', False)
        self._client_id = kwargs.pop('client_id', MS_TEAMS_CLIENT_ID)
        self._client_secret = kwargs.pop('client_secret', MS_TEAMS_CLIENT_SECRET)
        self._tenant_id = kwargs.pop('tenant_id', MS_TEAMS_TENANT_ID)
        self._team_id = kwargs.pop('team_id', MS_TEAMS_DEFAULT_TEAMS_ID)
        self._chat_id = kwargs.pop('chat_id', None)
        self.credentials: dict = {}
        if self.as_user:
            self.credentials = {
                "username": kwargs.pop('username', O365_USER),
                "password": kwargs.pop('password', O365_PASSWORD)
            }
        super(Teams, self).__init__(*args, **kwargs)

    async def close(self):
        pass

    def get_graph_client(self, client: Any, scopes: Optional[list] = None):
        if not scopes:
            scopes = self.scopes
        return GraphServiceClient(credentials=client, scopes=scopes)

    async def connect(self, *args, **kwargs):
        # getting MS graph access token:
        scopes = ["https://graph.microsoft.com/.default"]
        authority = f"https://login.microsoftonline.com/{self._tenant_id}"
        if self.as_user is True:
            self.app = msal.PublicClientApplication(
                self._client_id, authority=authority
            )
            # Acquire token using ROPC
            result = self.app.acquire_token_by_username_password(
                scopes=scopes,
                **self.credentials
            )
            self._client = UsernamePasswordCredential(
                tenant_id=self._tenant_id,
                client_id=self._client_id,
                **self.credentials
            )
        else:
            self.app = msal.ConfidentialClientApplication(
                self._client_id,
                authority=authority,
                client_credential=self._client_secret
            )
            result = self.app.acquire_token_for_client(
                scopes=scopes
            )
            self._client = ClientSecretCredential(
                tenant_id=self._tenant_id,
                client_id=self._client_id,
                client_secret=self._client_secret
            )
        try:
            self._token = result["access_token"]
            self._authentication = result
        except KeyError as exc:
            error = result.get("error")
            desc = result.get("error_description")
            _id = result.get("correlation_id")
            raise NotifyException(
                f"{_id}: {error}: {desc}"
            ) from exc
        # using the token to create a Graph Client:
        self._graph = self.get_graph_client(client=self._client, scopes=scopes)
        me = await self._graph.me.get()
        self._owner_id = me.id

    async def _render_(
        self,
        to: Actor = None,
        message: Union[str, TeamsCard] = None,
        _type: str = 'card',
        **kwargs
    ):  # pylint: disable=W0613
        """
        _render_.

        Returns the parseable version of Message template.
        """
        if isinstance(message, TeamsCard):
            if _type == 'card':
                # converting message to a dictionary
                payload = message.to_dict()
            else:
                card = {
                    "id": str(message.card_id),
                    "contentType": message.content_type,
                    "content": json.dumps(message.to_adaptative())
                }
                payload = {
                    "body": {
                        "contentType": "html",
                        "content": f"<attachment id=\"{message.card_id}\"></attachment>"
                    },
                    "attachments": [card]
                }
        elif isinstance(message, dict):
            # is already a dictionary
            payload = message
        elif isinstance(message, str):
            # is the text message
            payload = {
                "@type": "MessageCard",
                "@context": "http://schema.org/extensions",
                "text": message
            }
        else:
            raise RuntimeError(
                f"Invalid Message Type: {type(message)}"
            )
        # TODO: using Jinja Templates on Teams Cards.
        return payload

    async def _send_(self, to: Actor, message: Union[str, Any], **kwargs) -> Any:
        """_send_.
        Send message to Microsoft Teams channel using an incoming webhook.
        """
        result = None
        if isinstance(to, TeamsWebhook):
            # using webhook instead channel ID
            msg = await self._render_(to, message, _type='card', **kwargs)
            try:
                webhook_url = to.uri or MS_TEAMS_DEFAULT_WEBHOOK
            except (KeyError, ValueError):
                webhook_url = MS_TEAMS_DEFAULT_WEBHOOK
            result = await self.send_webhook(webhook_url, msg)
        else:
            msg = await self._render_(to, message, _type='adaptative', **kwargs)
            if isinstance(to, TeamsChannel):
                channel = to.channel_id
                team = to.team_id
                if not channel:
                    channel = MS_TEAMS_DEFAULT_CHANNEL_ID
                    team = MS_TEAMS_DEFAULT_TEAMS_ID
                # using graph to send messages to a channel.
                result = await self.send_message_to_channel(
                    team, channel, msg
                )
            if isinstance(to, TeamsChat):
                if chat := to.chat_id:
                    # using graph to send messages to a channel.
                    result = await self.send_message_to_chat(
                        chat, msg
                    )
                else:
                    raise NotifyException(
                        "Invalid Recipient Object: Need an string or a TeamsChat Object"
                    )
                # using graph to send messages to a channel.
                result = await self.send_message_to_chat(
                    chat, msg
                )
            elif isinstance(to, Actor):
                result = await self.send_direct_message(
                    to, msg
                )
            else:
                raise NotifyException(
                    "Invalid Recipient Object: Need an string or a TeamsChannel Object"
                )

        return result

    async def send_message_to_channel(self, team_id: str, channel_id: str, message: dict):
        headers = {
            'Authorization': f'Bearer {self._token}',
            'Content-Type': 'application/json'
        }
        message_url = f'https://graph.microsoft.com/v1.0/teams/{team_id}/channels/{channel_id}/messages'
        async with aiohttp.ClientSession() as session:
            async with session.post(message_url, headers=headers, json=message) as response:
                if response.status not in [200, 201]:
                    raise MessageError(
                        f"Teams: Error sending Notification: {await response.text()}"
                    )
                return await response.json()

    async def send_webhook(self, webhook_url: str, message: str):
        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook_url,
                data=json.dumps(message),
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status != 200:
                    raise MessageError(
                        f"Teams: Error sending Notification: {await response.text()}"
                    )
                return await response.text()

    async def send_message_to_chat(self, chat_id: str, message: Dict[str, Any]):
        """
        Generic method: send a message to an existing chat (group or one-on-one).
        """
        body = message.get("body", {})
        attachments_list = message.get("attachments", [])
        card_dict = {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.2",
            "speak": "Your meeting about \"Adaptive Card design session\" is starting at 12:30 pmDo you want to snooze or do you want to send a late notification to the attendees?",
            "body": [
                {
                    "type": "TextBlock",
                    "text": "Summary",
                    "size": "large",
                    "weight": "bolder",
                    "style": "heading",
                    "wrap": True
                },
                {
                    "type": "TextBlock",
                    "text": "Conf Room 112/3377 (10)",
                    "isSubtle": True,
                    "wrap": True
                },
                {
                    "type": "TextBlock",
                    "text": "12:30 - 01:30",
                    "isSubtle": True,
                    "spacing": "none",
                    "wrap": True
                },
                {
                "type": "Input.ChoiceSet",
                "id": "snooze",
                "label": "Snooze for",
                "value": "5",
                "choices": [
                    {
                    "title": "5 minutes",
                    "value": "5"
                    },
                    {
                    "title": "10 minutes",
                    "value": "10"
                    },
                    {
                    "title": "15 minutes",
                    "value": "15"
                    },
                    {
                    "title": "30 minutes",
                    "value": "30"
                    },
                    {
                    "title": "1 hour",
                    "value": "60"
                    },
                    {
                    "title": "2 hours",
                    "value": "120"
                    }
                ]
                }
            ],
            "actions": [
                {
                    "type": "Action.Submit",
                    "title": "Snooze",
                    "data": {
                        "x": "snooze"
                    }
                },
                {
                    "type": "Action.Submit",
                    "title": "I'll be late",
                    "data": {
                        "x": "late"
                    }
                }
            ]
        }
        request_body = ChatMessage(
            subject=None,
            body=ItemBody(
                content_type=BodyType.Html,
                content=body.get('content')
            ),
            attachments=[
                ChatMessageAttachment(
                    id=att.get("id"),
                    content_type=att.get("contentType", "application/vnd.microsoft.card.adaptive"),
                    content=json.dumps(card_dict),
                    content_url=None,
                    name=None,
                    thumbnail_url=None,
                )
                for att in attachments_list
            ]
        )
        print('BODY > ', request_body)
        return await self._graph.chats.by_chat_id(chat_id).messages.post(request_body)

    async def send_direct_message(self, recipient: Actor, message: Dict[str, Any]):
        """
        Send a direct (1:1) message to a user identified by email address.

        1) We get the user object (to retrieve user ID).
        2) We create a new chat or reuse an existing one (this sample always creates new).
        3) Post the message to /chats/{chatId}/messages.
        """
        user = await self.get_teams_user(recipient.account.address)
        user_id = user.id

        # 2) Create new chat (or find existing)
        chat_id = await self._get_chat(user_id)  # noqa
        if not chat_id:
            chat_id = await self._create_chat(self._owner_id, user_id)

        # 4) Send the message to chat
        return await self.send_message_to_chat(chat_id, message)

    async def _create_chat(self, owner, user_id: str) -> str:
        """
        Create a new chat with the specified user.
        """
        request_body = Chat(
            chat_type=ChatType.OneOnOne,
            members=[
                AadUserConversationMember(
                    # for 1st user (owner)
                    odata_type="#microsoft.graph.aadUserConversationMember",
                    roles=["owner"],
                    additional_data={
                        "user@odata.bind": f"https://graph.microsoft.com/beta/users('{owner}')"
                    },
                ),
                AadUserConversationMember(
                    # for 2nd user (owner)
                    odata_type="#microsoft.graph.aadUserConversationMember",
                    roles=["owner"],
                    additional_data={
                        "user@odata.bind": f"https://graph.microsoft.com/beta/users('{user_id}')"
                    },
                ),
            ],
        )
        result = await self._graph.chats.post(request_body)
        return result.id

    async def _get_chat(self, user_id: str) -> str:
        """
        Create a new chat with the specified user or return if it already exists.
        """
        # chats = []
        # chats = await self._graph.users.by_user_id(
        #     self._owner_id
        # ).chats.get()
        # if not chats.value:
        #     return None

        # for chat in chats.value:
        #     if not chat.members:
        #         continue
        #     member_ids = [m.user_id for m in chat.members]
        #     # If the target user is in there, that is our existing chat
        #     if user_id in member_ids:
        #         return chat
        query_params = ChatsRequestBuilder.ChatsRequestBuilderGetQueryParameters(
            filter="chatType eq 'oneOnOne'",
            expand=["members"],
        )

        request_configuration = RequestConfiguration(
            query_parameters=query_params,
        )

        chats = await self._graph.chats.get(
            request_configuration=request_configuration
        )
        if not chats.value:
            return None

        for chat in chats.value:
            if not chat.members:
                continue
            member_ids = [m.user_id for m in chat.members]
            # If the target user is in there, that is our existing chat
            if user_id in member_ids:
                return chat.id
        return None

    async def get_teams_user(self, email: str) -> Dict[str, Any]:
        """
        Retrieve a user from Microsoft Graph by email, returns the user object (JSON).
        """
        # Fetch the user info using the Graph client
        try:
            user_info = await self._graph.users.by_user_id(email).get()
            if not user_info:
                # trying to find a user
                users = await self._graph.users.get(
                    query_parameters={
                        "$filter": f"mail eq '{email}'"
                    }
                )
                if not users.value:
                    raise ValueError(f"No user found for {email}.")
                user_info = users.value[0]
            self.logger.info(
                f"Retrieved information for user: {email}"
            )
            return user_info
        except Exception as e:
            self.logger.error(
                f"Failed to retrieve user info for {email}: {e}"
            )
