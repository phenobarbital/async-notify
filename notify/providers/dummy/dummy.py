"""
Dummy.

"""
from typing import Any, Union
from collections.abc import Callable
from navconfig.logging import logging
from notify.utils import Msg
from notify.models import Actor
from notify.providers.abstract import ProviderBase, ProviderType


def dummy_sent(obj: ProviderBase, recipient: Actor, message: Union[str, Any], result: Any, **kwargs): # pylint: disable=W0613
    logging.debug(f'Message Sent! {recipient!s}')
    #


class Dummy(ProviderBase):
    """
    dummy.

    Dummy Provider to send messages to stdout
    """
    provider = 'dummy'
    provider_type = ProviderType.NOTIFY
    blocking: bool = True
    sent: Callable = dummy_sent

    async def connect(self, *args, **kwargs):
        print('Connecting to Dummy ...')

    async def close(self):
        print('Closing to Dummy...')

    async def _send_(self, to: Actor, message: Union[str, Any], subject: str = None, **kwargs):
        """
        _send.

        Logic associated with the construction of notifications
        """
        msg = await self._render_(to=to, message=message, **kwargs)
        try:
            Msg(str(msg))
        except TypeError:
            print(msg)
        return msg
