"""
onesignal.

Using OneSignal infraestructure to send push notifications to browsers.
"""
from notify.providers import ProviderIMBase, PUSH
from notify.settings import (
    ONESIGNAL_PLAYER_ID, ONESIGNAL_OS_APP_ID, ONESIGNAL_OS_API_KEY)
#from onesignalclient.app_client import OneSignalAppClient
#from onesignalclient.notification import Notification
from requests.exceptions import HTTPError


class Onesignal(ProviderIMBase):
    """
    onesignal.

    param:: player_ids: a list of "players", recipients of push messages
    param:: app_id: passing an APP_ID
    """
    provider = 'onesignal'
    provider_type = PUSH

    def __init__(self, player_ids=None, app_id=None, api_key=None, *args, **kwargs):
        """
        :param player_id: user token given by OneSignal API
        :param app_id:
        :param api_key:

        """
        super(Onesignal, self).__init__(*args, **kwargs)
        self.players = ONESIGNAL_PLAYER_ID if player_ids is None else player_ids
        self.os_app_id = ONESIGNAL_OS_APP_ID if app_id is None else app_id
        self.os_api_key = ONESIGNAL_OS_API_KEY if api_key is None else api_key

    def send(self):
        """
        Send push notification through OneSignal API

        """
        client = OneSignalAppClient(
            app_id=self.os_app_id,
            app_api_key=self.os_api_key
        )
        notification = self.onesignal_notify(self.players)
        result = client.create_notification(notification)
        try:
            # Sends it!
            result = client.create_notification(notification)
        except HTTPError as e:
            result = e.response.json()
        print(result)

    def onesignal_notify(self, players):
        """
        :param players: list of player ids to pass a notification to

        """
        notification = Notification(self.os_app_id, Notification.DEVICES_MODE)
        notification.include_player_ids = players
        return notification
