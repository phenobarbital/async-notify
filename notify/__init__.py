# -*- coding: utf-8 -*-
"""Async-Notify.

Asyncio-based Notifications connectors for NAV.
"""
import asyncio
import pkgutil
from pathlib import Path
import uvloop
from notify.settings import TEMPLATE_DIR
from notify.templates import TemplateParser
from notify.providers.abstract import ProviderType
from .notify import PROVIDERS, Notify, LoadProvider

from .version import (
    __title__, __description__, __version__, __author__, __author_email__
)

## more information
__copyright__ = 'Copyright (c) 2020-2022 Jesus Lara'
__license__ = 'BSD'

# install uvloop and set as default loop for asyncio.
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

__all__ = ('PROVIDERS', 'Notify', 'LoadProvider', 'ProviderType', )
TemplateEnv = None


if __name__ == "notify":
    # loading template parser:
    TemplateEnv = TemplateParser(
        directory=TEMPLATE_DIR
    )
