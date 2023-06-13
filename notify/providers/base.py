"""Base.

Base Factory classes for all kind of Providers.
"""
import asyncio
import time
from abc import ABC, abstractmethod
from enum import Enum
from functools import partial
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Union, Optional
from collections.abc import Awaitable, Callable
from navconfig import config, DEBUG
from navconfig.logging import logging
from notify.types import SafeDict
from notify.exceptions import (
    ProviderError,
    MessageError
)
from notify.models import Actor


class ProviderType(Enum):
    NOTIFY = "notify"  # generic notification
    SMS = "sms"  # SMS messages
    EMAIL = "email"  # email (smtp) notifications
    PUSH = "push"  # push notifications
    IM = "im"  # instant messaging


class ProviderBase(ABC):
    """ProviderBase.

    Base class for All providers
    """

    provider: str = None
    provider_type: ProviderType = ProviderType.NOTIFY
    blocking: bool = True
    sent: Optional[Union[Callable, Awaitable]] = None
