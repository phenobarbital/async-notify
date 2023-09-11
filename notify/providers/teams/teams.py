from typing import Union, Any
import json
import aiohttp
import msal
from navconfig.logging import logging
from notify.models import Actor, TeamsWebhook, TeamsChannel, TeamsCard
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
        self.credentials: dict = {}
        if self.as_user is True:
            self.credentials = {
                "username": kwargs.pop('username', O365_USER),
                "password": kwargs.pop('password', O365_PASSWORD)
            }
        super(Teams, self).__init__(*args, **kwargs)

    async def close(self):
        pass

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
        else:
            self.app = msal.ConfidentialClientApplication(
                self._client_id,
                authority=authority,
                client_credential=self._client_secret
            )
            result = self.app.acquire_token_for_client(
                scopes=scopes
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
        # print('PAYLOAD IS > ', payload)
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
                webhook_url = to.uri
                if not webhook_url:
                    webhook_url = MS_TEAMS_DEFAULT_WEBHOOK
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
            else:
                raise NotifyException(
                    "Invalid Recipient Object: Need an string or a TeamsChannel Object"
                )
            # using graph to send messages to a channel.
            result = await self.send_message(
                team, channel, msg
            )
        return result

    async def send_message(self, team_id: str, channel_id: str, message: dict):
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
