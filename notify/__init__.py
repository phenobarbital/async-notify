# -*- coding: utf-8 -*-
"""Async-Notify.

Asyncio-based Notifications connectors for NAV.
"""
from .providers.base import ProviderType
from .notify import Notify
from .utils.uv import install_uvloop

# Use uvloop opportunistically when the optional dependency is installed.
install_uvloop()

__all__ = (
    "Notify",
    "ProviderType",
)
