"""
Twitter API.

Using tweepy to send (publish) Tweets.
"""
from typing import (
    Optional,
    Union,
    Any
)
import tweepy
from notify.providers import ProviderIMBase, ProviderType
from notify.models import Actor
from notify.exceptions import ProviderError
from .settings import TWITTER_ACCESS_TOKEN, TWITTER_TOKEN_SECRET, TWITTER_CONSUMER_KEY, TWITTER_CONSUMER_SECRET


class Twitter(ProviderIMBase):
    provider = 'twitter'
    provider_type = ProviderType.IM
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
        self._secret = TWITTER_TOKEN_SECRET if secret is None else kwargs['sid']
        self._consumer_key = TWITTER_CONSUMER_KEY if consumer_key is None else consumer_key
        self._consumer_secret = TWITTER_CONSUMER_SECRET if consumer_secret is None else consumer_secret

    def close(self):
        self.client = None

    def connect(self):
        """
        Verifies that a token and sid were given

        """
        if self._token is None or self._secret is None:
            raise RuntimeError(
                f'to send Tweets via {self._token} you need to configure TWITTER_ACCESS_TOKEN & TWITTER_TOKEN_SECRET in \n'
                'environment variables or send properties to theinstance.'
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
            raise ProviderError(
                f'Twitter API error: {err}'
            ) from err
        # determine actor:
        self.actor = self.client.me()


    async def _send_(self, to: Optional[Actor] = None, message: Union[str, Any] = None, **kwargs) -> Any:
        """
        _send_.

        Publish a Twitter using Tweepy
        :param to: Optional Reply-To Message.
        :param message: message to Publish
        """
        try:
            msg = self._render(to, message, **kwargs)
            result = self.client.update_status(status=msg)
            # TODO: processing the output, adding callbacks
            return result
        except Exception as ex:
            print(ex)
            raise ProviderError(
                f'Error Publishing Tweet, Current Error: {ex}'
            ) from ex
