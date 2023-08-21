from typing import Union, Any
import json
import aiohttp
from notify.models import Actor, TeamsWebhook, TeamsChannel, TeamsCard
from notify.providers.base import ProviderIM, ProviderType
from notify.conf import (
    # Bot information:
    TEAMS_DEFAULT_CHANNEL
)
from notify.exceptions import MessageError

class Teams(ProviderIM):
    """
    Teams.

    Send messages to a channel using Teams.
    """
    provider = "teams"
    provider_type = ProviderType.IM
    blocking: str = 'asyncio'

    async def close(self):
        pass

    async def connect(self):
        # getting MS graph access token:
        pass

    async def _render_(
        self, to: Actor = None, message: Union[str, TeamsCard] = None, subject: str = None, **kwargs
    ):  # pylint: disable=W0613
        """
        _render_.

        Returns the parseable version of Message template.
        """
        if isinstance(message, TeamsCard):
            # converting message to a dictionary
            payload = message.to_dict()
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
        msg = await self._render_(to, message, **kwargs)
        result = None
        if isinstance(to, TeamsWebhook):
            # using webhook instead channel ID
            webhook_url = to.uri
            result = await self.send_webhook(webhook_url, msg)
        if isinstance(to, TeamsChannel):
            webhook_url = to.uri
        elif isinstance(to, str):
            webhook_url = to
        else:
            webhook_url = TEAMS_DEFAULT_CHANNEL
        # using graph to send messages to a channel.
        return result

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
