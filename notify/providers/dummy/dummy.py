"""
Dummy.

"""
from notify.utils import colors, SafeDict
from pprint import pprint
from notify.providers import ProviderBase, NOTIFY
from notify.models import Actor
from typing import List, Dict, Optional, Union, Awaitable

class Dummy(ProviderBase):
    """
    dummy.

    Dummy Provider to send messages to stdout
    """
    provider = 'dummy'
    provider_type = NOTIFY
    longrunning = False

    def connect(self):
        print('Connecting ...')

    def close(self):
        print('Closing ...')

    async def _send(self, to: Actor, message: str, **kwargs):
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
