from notify.settings import TWILIO_AUTH_TOKEN, TWILIO_ACCOUNT_SID, TWILIO_PHONE
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client
from notify.providers import ProviderMessageBase, SMS
from notify.models import Actor

class Twilio(ProviderMessageBase):
    provider = 'sms'
    provider_type = SMS
    level = ''
    _msg = ''
    client = None
    token = None
    sid = None

    def __init__(self, sid=None, token=None, *args, **kwargs):
        """
        :param token: twilio auth token given by Twilio
        :param sid: twilio auth id given by Twilio

        """
        super(Twilio, self).__init__(*args, **kwargs)
        self.token = TWILIO_AUTH_TOKEN if token is None else token
        self.sid = TWILIO_ACCOUNT_SID if sid is None else sid
        self.connect()

    def close(self):
        self.client = None

    def connect(self):
        """
        Verifies that a token and sid were given

        """
        if self.token is None or self.sid is None:
            raise RuntimeError(
                'to send SMS via {0} you need to configure TWILIO_ACCOUNT_SID & TWILIO_AUTH_TOKEN in \n'
                'environment variables or send account_sid & auth_token in instance.'.format(self.id)
            )
        self.client = Client(self.sid, self.token)

    async def _send(self, to: Actor, message: str, **kwargs):
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
        except TwilioRestException as e:
            print(e)
            raise RuntimeError(
                'Error Sending SMS on Twilio, current error: {}'.format(e)
            )
