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
from .notify import PROVIDERS, Notify, LoadProvider
from notify.providers.abstract import ProviderType

## more information
__copyright__ = 'Copyright (c) 2020-2022 Jesus Lara'
__license__ = 'BSD'

# install uvloop and set as default loop for asyncio.
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

__all__ = [ 'PROVIDERS', 'Notify', 'LoadProvider', 'ProviderType', ]
TemplateEnv = None


if __name__ == "notify":
    path = Path(__file__).parent.joinpath('providers')
    # directory for notify providers
    for loader, name, ispkg in pkgutil.iter_modules([str(path)]):
        if ispkg is True:
            __all__.append(name)
            cls = LoadProvider(name)
            PROVIDERS[name] = cls
    # loading template parser:
    TemplateEnv = TemplateParser(
        directory=TEMPLATE_DIR
    )
