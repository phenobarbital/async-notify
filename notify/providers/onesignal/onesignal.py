"""
onesignal.

Using OneSignal infraestructure to send push notifications to browsers.
"""
from typing import (
    Union,
    Any
)
from requests.exceptions import HTTPError
from onesignal_sdk.client import AsyncClient
from onesignal_sdk.error import OneSignalHTTPError
from notify.providers.abstract import ProviderIMBase, ProviderType
from notify.models import Actor
from notify.exceptions import ProviderError
from .settings import (
    ONESIGNAL_PLAYER_ID,
    ONESIGNAL_OS_APP_ID,
    ONESIGNAL_OS_API_KEY
)



class Onesignal(ProviderIMBase):
    """
    onesignal.

    param:: player_ids: a list of "players", recipients of push messages
    param:: app_id: passing an APP_ID
    """
    provider = 'onesignal'
    provider_type = ProviderType.PUSH
    blocking: bool = False

    def __init__(self, player_ids: str = None, app_id: str = None, api_key: str = None, *args, **kwargs):
        """
        :param player_id: user token given by OneSignal API
        :param app_id:
        :param api_key:

        """
        super(Onesignal, self).__init__(*args, **kwargs)
        self.players = ONESIGNAL_PLAYER_ID if player_ids is None else player_ids
        self.os_app_id = ONESIGNAL_OS_APP_ID if app_id is None else app_id
        self.os_api_key = ONESIGNAL_OS_API_KEY if api_key is None else api_key
        self.client = None


    async def connect(self):
        try:
            self.client = AsyncClient(
                app_id=self.os_app_id,
                rest_api_key=self.os_api_key
            )
        except Exception as err:
            self._logger.error(err)
            raise ProviderError(
                f"Error connecting to OneSignal API {err}"
            ) from err


    async def _send_(self, to: Actor, message: Union[str, Any], **kwargs) -> Any:
        """_send_.
        Send push notification through OneSignal API.
        """
        notification_body = {
            'contents': {'en': message},
            'included_segments': ['Active Users'],
        }
        try:
            # Sends it!
            response = await self.client.send_notification(notification_body)
            print(response.body) # JSON parsed response
            print(response.status_code) # Status code of response
            print(response.http_response) # Original http response object.
            return response
        except OneSignalHTTPError as e: # An exception is raised if response.status_code != 2xx
            print(e)
            print(e.status_code)
            print(e.http_response.json()) # You can see the details of error by parsing original response
        except HTTPError as e:
            result = e.response.json()
            print(result)
