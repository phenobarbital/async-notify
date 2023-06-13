# -*- coding: utf-8 -*-
"""Async-Notify.

Asyncio-based Notifications connectors for NAV.
"""
import asyncio
import uvloop
from notify.conf import TEMPLATE_DIR
from notify.templates import TemplateParser
from notify.providers.abstract import ProviderType
from .notify import Notify

# install uvloop and set as default loop for asyncio.
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
uvloop.install()

__all__ = (
    "Notify",
    "ProviderType",
)

TemplateEnv = None

if __name__ == "notify":
    # loading template parser:
    TemplateEnv = TemplateParser(
        directory=TEMPLATE_DIR
    )
