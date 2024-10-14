"""
Onesignal.

Using OneSignal infrastructure to send push notifications to browsers.
"""
from typing import Union, Any
from requests.exceptions import HTTPError
from onesignal_sdk.client import AsyncClient
from onesignal_sdk.error import OneSignalHTTPError
from notify.providers.base import ProviderIMBase, ProviderType
from notify.models import Actor
from notify.exceptions import ProviderError
from notify.conf import ONESIGNAL_PLAYER_ID, ONESIGNAL_OS_APP_ID, ONESIGNAL_OS_API_KEY


class Onesignal(ProviderIMBase):
    """
    onesignal.

    param:: player_ids: a list of "players", recipients of push messages
    param:: app_id: passing an APP_ID
    """

    provider = "onesignal"
    provider_type = ProviderType.PUSH
    blocking: str = 'asyncio'

    def __init__(
        self,
        player_ids: str = None,
        app_id: str = None,
        api_key: str = None,
        *args,
        **kwargs,
    ):
        """
        :param player_ids: user token given by OneSignal API
        :param app_id: OneSignal App ID
        :param api_key: OneSignal API Key
        """
        super(Onesignal, self).__init__(*args, **kwargs)
        self.players = ONESIGNAL_PLAYER_ID if player_ids is None else player_ids
        self.os_app_id = ONESIGNAL_OS_APP_ID if app_id is None else app_id
        self.os_api_key = ONESIGNAL_OS_API_KEY if api_key is None else api_key
        self.client = None

    async def connect(self):
        """
        Connects to the OneSignal API using the AsyncClient.
        """
        try:
            self.client = AsyncClient(
                app_id=self.os_app_id, rest_api_key=self.os_api_key
            )
        except Exception as err:
            self._logger.error(f"Error connecting to OneSignal API: {err}")
            raise ProviderError(f"Error connecting to OneSignal API {err}") from err

    async def close(self):
        """
        Closes the OneSignal API connection (if applicable).
        """
        if self.client:
            # Assuming there is a close method or any other cleanup logic for the client
            self.client = None

    async def _send_(self, to: Actor, message: Union[str, Any], **kwargs) -> Any:
        """_send_.
        Send push notification through OneSignal API.
        """
        notification_body = {
            "contents": {"en": message},
            "include_player_ids": [self.players],  # Sending to specific players
            "included_segments": ["Active Users"]  # Segments can be controlled
        }
        try:
            # Sends the push notification!
            response = await self.client.send_notification(notification_body)
            self._logger.debug(f"OneSignal response: {response.body}")  # JSON parsed response
            self._logger.debug(f"OneSignal status code: {response.status_code}")  # Status code
            return response
        except OneSignalHTTPError as e:
            self._logger.error(f"OneSignal HTTP Error: {e}")
            raise ProviderError(f"OneSignal HTTP Error: {e}") from e
        except HTTPError as e:
            result = e.response.json()
            self._logger.error(f"HTTP Error: {result}")
            raise ProviderError(f"HTTP Error: {result}") from e
        except Exception as e:
            self._logger.exception(f"Error while sending OneSignal push notification: {e}")
            raise ProviderError(f"Unexpected Error: {e}") from e

    async def send(
        self,
        recipient: list[Actor] = None,
        message: Union[str, Any] = None,
        subject: str = None,
        **kwargs,
    ):
        """
        Main method to send push notifications to a list of recipients.
        """
        results = []
        recipients = [recipient] if not isinstance(recipient, list) else recipient
        # Iterate over recipients and send push notifications
        for to in recipients:
            try:
                result = await self._send_(to, message, **kwargs)
                results.append(result)
            except Exception as e:
                self._logger.error(f"Failed to send to {to}: {e}")
        return results
