
from typing import (
    Union,
    Any
)
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client
from notify.providers.abstract import ProviderMessageBase, ProviderType
from notify.models import Actor
from notify.exceptions import ProviderError
from .settings import TWILIO_AUTH_TOKEN, TWILIO_ACCOUNT_SID, TWILIO_PHONE

class Twilio(ProviderMessageBase):
    provider = 'sms'
    provider_type = ProviderType.SMS
    level = ''

    def __init__(self, sid: str = None, token: str = None, **kwargs):
        """
        :param token: twilio auth token given by Twilio
        :param sid: twilio auth id given by Twilio

        """
        self._msg = None
        self.client = None
        super(Twilio, self).__init__(**kwargs)
        self.token = TWILIO_AUTH_TOKEN if token is None else token
        self.sid = TWILIO_ACCOUNT_SID if sid is None else sid

    def close(self):
        self.client = None

    def connect(self):
        """
        Verifies that a token and sid were given

        """
        if self.token is None or self.sid is None:
            raise RuntimeError(
                f'to send SMS via {self.__name__} you need to configure TWILIO_ACCOUNT_SID & TWILIO_AUTH_TOKEN in \n'
                'environment variables or send account_sid & auth_token in instance.'
            )
        self.client = Client(self.sid, self.token)

    async def _send_(self, to: Actor, message: Union[str, Any], **kwargs) -> Any:
        """
        _send.

        Send a text message using twilio
        :param to: recipient number
        :param message: message to send
        """
        try:
            data = self._render(to, message, **kwargs)
            phone = to.account['phone']
            msg = self.client.messages.create(to=phone, from_=TWILIO_PHONE, body=data)
            #print(msg)
            #print(msg.sid)
            # TODO: processing the output, adding callbacks
            return msg
        except TwilioRestException as ex:
            print(ex)
            raise ProviderError(
                f'Error Sending SMS on Twilio, current error: {ex}'
            ) from ex
