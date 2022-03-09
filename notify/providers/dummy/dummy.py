"""
Dummy.

"""
import logging
from notify.utils import colors, Msg
from notify.providers.abstract import ProviderBase, ProviderType
from notify.models import Actor
from typing import Any, Callable, List, Dict, Optional, Union, Awaitable


def dummy_sent(recipient: Actor, message: Union[str, Any], result: Any, task: Any, *args, **kwargs):
    logging.debug(f'Message Sent! {recipient!s}')
    Msg(message)


class Dummy(ProviderBase):
    """
    dummy.

    Dummy Provider to send messages to stdout
    """
    provider = 'dummy'
    provider_type = ProviderType.NOTIFY
    blocking = False
    sent: Callable = dummy_sent

    def connect(self):
        print('Connecting to Dummy ...')

    def close(self):
        print('Closing to Dummy...')

    async def _send(self, to: Actor, message: Union[str, Any], **kwargs):
        """
        _send.

        Logic associated with the construction of notifications
        """
        msg = self._render(to, message, **kwargs)
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
        print(coloring + msg, colors.reset)
        return True
