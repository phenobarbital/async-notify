"""
Slack.

Using Slack infraestructure to send messages to Slack Client.
"""
from typing import Union, Any
from collections.abc import Callable
# Slack API
from slack_bolt.authorization import AuthorizeResult
# from slack_bolt.async_app import AsyncApp
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError

# notify
from navconfig.logging import logging
from notify.providers.base import ProviderIM, ProviderType
from notify.models import Actor, Channel
from notify.exceptions import ProviderError, MessageError
from notify.conf import (
    # Bot information:
    SLACK_TEAM_ID,
    SLACK_BOT_TOKEN,
    SLACK_DEFAULT_CHANNEL,
)


async def authorize(enterprise_id, team_id, user_id, client: AsyncWebClient, logger):
    logger.info(f"{enterprise_id},{team_id},{user_id}")
    # You can implement your own logic here
    return AuthorizeResult.from_auth_test_response(
        auth_test_response=await client.auth_test(token=SLACK_BOT_TOKEN),
        bot_token=SLACK_BOT_TOKEN,
    )


class Slack(ProviderIM):
    """
    Slack.

    param:: player_ids: a list of "players", recipients of push messages
    param:: app_id: passing an APP_ID
    """
    provider = "slack"
    provider_type = ProviderType.IM
    blocking: str = 'asyncio'

    def __init__(self, *args, **kwargs):
        """
        :param player_id: user token given by OneSignal API
        :param app_id:
        :param api_key:

        """
        self.client: Callable = None
        self.app: Callable = None
        self.conversations: list = []
        super(Slack, self).__init__(*args, **kwargs)

    async def connect(self, **kwargs):
        try:
            # self.app = AsyncApp(signing_secret=SLACK_SIGNING_SECRET, authorize=authorize)
            logger = logging.getLogger(__name__)
            logger.setLevel(logging.INFO)
            self.client = AsyncWebClient(
                token=SLACK_BOT_TOKEN, logger=logger, team_id=SLACK_TEAM_ID
            )
            self.conversations = await self.client.conversations_list(
                limit=10, team_id=SLACK_TEAM_ID
            )
        except Exception as err:
            self._logger.error(err)
            raise ProviderError(
                f"Error connecting to Slack API {err}"
            ) from err

    async def close(self):
        self.client = None
        self.app = None

    async def _send_(self, to: Actor, message: Union[str, Any], **kwargs) -> Any:
        """_send_.
        Send push notification through OneSignal API.
        """
        if isinstance(to, Channel):
            # send directly to a channel:
            channel = to.channel_id
        else:
            print("AQUI ", to, to.account)
            try:
                # getting User ID for Slack Account:
                channel = to.account.userid if to.account.provider == "slack" else None
            except (TypeError, AttributeError, KeyError) as e:
                print("ERR ", e)
                channel = None
            try:
                channel = kwargs["channel"]
            except KeyError:
                channel = SLACK_DEFAULT_CHANNEL
        msg = await self._render_(to, message, **kwargs)
        notification_body = {"channel": channel, "text": msg}
        try:
            # Sends it!
            response = await self.client.chat_postMessage(**notification_body)
            return response
            # if response.status_code == 200:
            #     print(response.body) # JSON parsed response
            #     return response
            # else:
            #     raise MessageError(
            #         f"Slack: Error sending Notification: {response.http_response}",
            #         payload=response
            #     )
        except (
            SlackApiError
        ) as ex:  # An exception is raised if response.status_code != 2xx
            raise MessageError(
                f"Slack: Error sending Notification: {ex}",
            ) from ex
        except Exception as ex:
            raise ProviderError(
                f"Slack: Exception on Slack Client: {ex}"
            ) from ex
