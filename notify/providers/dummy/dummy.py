"""
Dummy.

"""
from typing import Any, Union
from collections.abc import Callable
from navconfig.logging import logging
from notify.utils import colors, Msg
from notify.models import Actor
from notify.providers.abstract import ProviderBase, ProviderType


def dummy_sent(recipient: Actor, message: Union[str, Any], result: Any, task: Any, **kwargs): # pylint: disable=W0613
    print('RECEIVED ', recipient, message, result, task, kwargs)
    logging.debug(f'Message Sent! {recipient!s}')
    Msg(message)


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

    async def _send_(self, to: Actor, message: Union[str, Any], **kwargs):
        """
        _send.

        Logic associated with the construction of notifications
        """
        msg = await self._render_(to=to, message=message, **kwargs)
        try:
            level = kwargs['level']
        except KeyError:
            level = 'INFO'
        if level == 'INFO':
            coloring = colors.bold + colors.fg.green
        elif level == 'DEBUG':
            coloring = colors.fg.lightblue
        elif level == 'WARN':
            coloring = colors.bold + colors.fg.yellow
        elif level == 'ERROR':
            coloring = colors.fg.lightred
        elif level == 'CRITICAL':
            coloring = colors.bold + colors.fg.red
        else:
            coloring = colors.reset
        print(coloring + str(msg), colors.reset)
        return msg
