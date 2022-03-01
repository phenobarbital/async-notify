# -*- coding: utf-8 -*-
"""Async-Notify.

Asyncio-based Notifications connectors for NAV.
"""
import asyncio
import uvloop
import pkgutil
from pathlib import Path
from .version import (
    __title__, __description__, __version__, __author__, __author_email__
)
from notify.settings import TEMPLATE_DIR
from notify.templates import TemplateParser
from .exceptions import ProviderError, notifyException
from .notify import PROVIDERS, Notify, LoadProvider

# install uvloop and set as default loop for asyncio.
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
uvloop.install()

__all__ = [ 'PROVIDERS', 'Notify', 'LoadProvider',  ]
TemplateEnv = None

if __name__ == "notify":
    print('THIS CODE IS CALLED')
    path = Path(__file__).parent.joinpath('providers')
    # directory for notify providers
    for (_, name, _) in pkgutil.iter_modules([str(path)]):
        cls = LoadProvider(name)
        PROVIDERS[name] = cls
    # loading template parser:
    TemplateEnv = TemplateParser(
        directory=TEMPLATE_DIR
    )
