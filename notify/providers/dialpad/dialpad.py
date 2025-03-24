import aiohttp
import json
from typing import Any, Union
from collections.abc import Callable
from navconfig.logging import logging
from notify.providers.base import ProviderMessaging, ProviderType
from notify.models import Actor
from notify.exceptions import ProviderError
from notify.conf import (
    DIALPAD_APIKEY,
    DIALPAD_FROM_NUMBER
)

class Dialpad(ProviderMessaging):
    provider = "dialpad"
    provider_type = ProviderType.SMS
    level = ""
    blocking: str = 'asyncio'
    session = None

    def __init__(self, sid: str = None, token: str = None, **kwargs):
        """
        :param token: dialpad auth token given by Dialpad
        :param from_number: dialpad from number

        """
        self._msg = None
        super(Dialpad, self).__init__(**kwargs)
        self.token = DIALPAD_APIKEY if token is None else token
        self.from_number = DIALPAD_APIKEY if kwargs.get('from_number') is None else kwargs.get('from_number')
        
    async def connect(self, *args, **kwargs):
        if self.token is None or self.from_number is None:
            raise RuntimeError(
                f"to send SMS via {self.__name__} you need to configure \
                DIALPAD_APIKEY and DIALPAD_FROM_NUMBER in environment\n \
                variables or send token and from_number as parameters in instance."
            )
        headers = {
            "accept": "application/json",
            "content-type": "application/json"
        }
        self.timeout = aiohttp.ClientTimeout(total=60)
        self.session = aiohttp.ClientSession(headers=headers, timeout=self.timeout)

    async def close(self):
        await self.session.close()

    async def _send_(
        self, to: Actor, message: Union[str, Any], subject: str = None, **kwargs
    ):
        try:
            url = f"https://dialpad.com/api/v2/sms?apikey={self.token}"

            message = await self._render_(to, message, **kwargs)
            phone = to.account["number"]
            data = {
                "infer_country_code": True,
                "from_number": DIALPAD_FROM_NUMBER,
                "to_numbers": [phone],
                "text": message
            }
            response = await self.session.post(url, data=json.dumps(data))
            res = await response.json()
            logging.debug(f"Sent to: {to.account!s} <> Result: {res!s}")
            return res
        except Exception as ex:
            raise ProviderError(
                f"Error Sending SMS on Dialpad, current error: {ex}"
            ) from ex
