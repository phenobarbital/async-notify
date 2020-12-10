"""
Twitter API.

Using tweepy to send (publish) Tweets.
"""
from notify.settings import TWITTER_ACCESS_TOKEN, TWITTER_TOKEN_SECRET, TWITTER_CONSUMER_KEY, TWITTER_CONSUMER_SECRET
from notify.providers import ProviderIMBase, IM
from typing import List, Optional
from notify.models import Actor, Chat
import tweepy

class Twitter(ProviderIMBase):
    provider = 'twitter'
    provider_type = IM
    _consumer_key: str = None
    _consumer_secret: str = None
    _token: str = None
    _secret: str = None
    client = None

    sid = None

    def __init__(
            self,
            consumer_key=None,
            consumer_secret=None,
            token=None,
            secret=None,
            *args,
            **kwargs
        ):
        """
        :param token: twilio auth token given by Twilio
        :param sid: twilio auth id given by Twilio

        """
        super(Twitter, self).__init__(*args, **kwargs)
        self._token = TWITTER_ACCESS_TOKEN if token is None else token
        self._secret = TWITTER_TOKEN_SECRET if secret is None else sid
        self._consumer_key = TWITTER_CONSUMER_KEY if consumer_key is None else consumer_key
        self._consumer_secret = TWITTER_CONSUMER_SECRET if consumer_secret is None else consumer_secret
        self.connect()

    def close(self):
        self.client = None

    def connect(self):
        """
        Verifies that a token and sid were given

        """
        if self._token is None or self._secret is None:
            raise RuntimeError(
                'to send Tweets via {0} you need to configure TWITTER_ACCESS_TOKEN & TWITTER_TOKEN_SECRET in \n'
                'environment variables or send properties to theinstance.'.format(self._token)
            )
        try:
            auth = tweepy.OAuthHandler(
                self._consumer_key,
                self._consumer_secret
            )
            if auth:
                auth.set_access_token(self._token, self._secret)
                self.client = tweepy.API(auth)
        except Exception as err:
            raise RuntimeError('Twitter API error: {}'.format(err))
        # determine actor:
        self.actor = self.client.me()

    async def _send(self, to: Optional[Actor] = None, message: str = '', **kwargs):
        """
        _send.

        Publish a Twitter using Tweepy
        :param to: Optional Reply-To Message.
        :param message: message to Publish
        """
        try:
            msg = self._render(to, message, **kwargs)
            result = self.client.update_status(status=msg)
            # TODO: processing the output, adding callbacks
            return result
        except Exception as e:
            print(e)
            raise RuntimeError(
                'Error Publishing Tweet, Current Error: {}'.format(e)
            )
