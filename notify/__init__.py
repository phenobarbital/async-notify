# -*- coding: utf-8 -*-
"""Async-Notify.

Asyncio-based Notifications connectors for NAV.
"""
import asyncio
import uvloop
from .providers.base import ProviderType
from .notify import Notify

# install uvloop and set as default loop for asyncio.
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
uvloop.install()

__all__ = (
    "Notify",
    "ProviderType",
)
