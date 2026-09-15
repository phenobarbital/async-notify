"""
Abstract Wrapper Base.

Any other wrapper extends this.
"""
from typing import Any
from collections.abc import Coroutine, Callable
import uuid
from datamodel import BaseModel
from navconfig.logging import logging
from notify import Notify
from notify.exceptions import MessageError
from notify.models import Actor, Chat, Channel, TeamsChannel


coro = Callable[[int], Coroutine[Any, Any, str]]

#: Kwargs that must never reach a queued notification payload. Currently
#: just the On-Behalf-Of user assertion (FEAT-004, M10): it is a live user
#: token, so it must never be serialized into Redis/TCP and must instead be
#: passed directly to `send(user_assertion=...)`.
QUEUE_FORBIDDEN_KWARGS: frozenset[str] = frozenset({"user_assertion"})


def reject_queued_secrets(message: dict) -> None:
    """Raise `MessageError` if a queued notification carries a forbidden secret kwarg.

    Checks both the top-level `message` dict keys and, when present, its
    nested `kwargs` dict — queued payloads may carry provider kwargs under
    either shape depending on the caller.

    Args:
        message: The payload about to be serialized/queued.

    Raises:
        MessageError: Naming the offending key — e.g. "user_assertion cannot
            be queued; send On-Behalf-Of mail directly" — never its value.
    """
    forbidden = QUEUE_FORBIDDEN_KWARGS & message.keys()
    nested_kwargs = message.get("kwargs")
    if isinstance(nested_kwargs, dict):
        forbidden = forbidden | (QUEUE_FORBIDDEN_KWARGS & nested_kwargs.keys())
    if forbidden:
        key = sorted(forbidden)[0]
        raise MessageError(
            f"{key} cannot be queued; send On-Behalf-Of mail directly instead of through the notify server."
        )


class NotifyWrapper:
    """
    A Wrapper class for Notify objects to manage and send notifications asynchronously.

    This class creates an instance of Notify object and provides a mechanism
    to send the notification in an asynchronous manner via the `__call__` method.

    Attributes:
        _id (uuid.UUID): The unique identifier for each NotifyWrapper instance.
        recipients (list): A list of recipients for the notification.
        notify (coro): An instance of Notify object for sending notifications.
        args (tuple): Additional positional arguments for the Notify object.
        kwargs (dict): Additional keyword arguments for the Notify object.
        loop (asyncio.AbstractEventLoop): Event loop in which the notification will be sent.

    Methods:
        call(): Asynchronous method to send the notification.
        __call__(): Special method to make the object callable, which triggers the `call()` method.
        set_loop(event_loop): Method to set the event loop in which the notification will be sent.
    """
    _debug: bool = False

    def __init__(self, provider: str, *args, **kwargs):
        reject_queued_secrets({**kwargs})
        self._id = str(uuid.uuid4())
        self.recipients: list = []
        recipients = kwargs.pop('recipient', [])
        rcpt = []
        for recipient in recipients:
            if isinstance(recipient, dict):
                if 'chat_id' in recipient:
                    rcpt.append(Chat(**recipient))
                elif 'team_id' in recipient:
                    rcpt.append(TeamsChannel(**recipient))
                elif 'channel_id' in recipient:
                    rcpt.append(Channel(**recipient))
                else:
                    rcpt.append(Actor(**recipient))
            elif isinstance(recipient, BaseModel):
                rcpt.append(recipient)
            else:
                print(f'Recipient {recipient} discarded.')
        self.recipients = rcpt
        self.loop = None
        # provider to be handled:
        self._provider = provider
        self.args = args
        self.kwargs = kwargs

    def __repr__(self):
        return f"<Notify:{self._provider!r}>"

    async def call(self):
        try:
            notify: coro = Notify(self._provider, **self.kwargs)
            async with notify as client:  # pylint: disable=E1701 # noqa
                return await client.send(
                    recipient=self.recipients,
                    *self.args[1:], **self.kwargs
                )
        except Exception as exc:
            logging.error(f'Unable to Send: {exc}')
            raise

    async def __call__(self):
        try:
            notify: coro = Notify(self._provider, **self.kwargs)
            async with notify as client:  # pylint: disable=E1701 # noqa
                return await client.send(
                    recipient=self.recipients,
                    *self.args, **self.kwargs
                )
        except Exception as exc:
            logging.error(f'Unable to Send: {exc}')
            raise

    @property
    def uid(self):
        return self._id
