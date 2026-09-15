"""Offline tests for the ProviderEmail opt-in hooks (FEAT-004, M5).

Covers `batch_recipients`, `raise_errors`, and `redacted_send_kwargs`, and
proves the defaults reproduce today's per-recipient, error-swallowing
behavior exactly (AC13: `email`/`gmail`/`smtp`/`sendgrid`/`ses` unaffected).
"""

import pytest

from notify.exceptions import ProviderError
from notify.models import Account, Actor
from notify.providers.mail import ProviderEmail


class _DummyMailProvider(ProviderEmail):
    """A minimal ProviderEmail subclass for offline hook testing."""

    provider = "dummy_mail"

    def __init__(self, *args, **kwargs):
        self.connect_error: Exception = None
        self.send_error: Exception = None
        self.fail_for_name: str = None
        self.send_calls: list = []
        self.sent_calls: list = []
        super().__init__(*args, **kwargs)

    async def connect(self, *args, **kwargs):
        if self.connect_error is not None:
            raise self.connect_error

    async def close(self):
        pass

    async def _prepare_(self, recipient=None, message=None, **kwargs):
        return message

    async def _send_(self, to, message, subject=None, **kwargs):
        self.send_calls.append((to, message, kwargs))
        target_name = to.name if isinstance(to, Actor) else None
        if self.send_error is not None and (self.fail_for_name is None or self.fail_for_name == target_name):
            raise self.send_error
        return {"to": to, "message": message}

    async def __sent__(self, recipient, message, result, **kwargs):
        self.sent_calls.append((recipient, message, result, kwargs))
        await super().__sent__(recipient, message, result, **kwargs)


@pytest.fixture
def actors() -> list[Actor]:
    return [
        Actor(name="Alice", account=Account(address="alice@contoso.com")),
        Actor(name="Bob", account=Account(address="bob@contoso.com")),
    ]


async def test_email_hooks_default_unchanged(actors):
    """Defaults: one _send_ per recipient, exceptions logged and swallowed."""
    provider = _DummyMailProvider()
    provider.send_error = RuntimeError("boom for bob")
    provider.fail_for_name = "Bob"

    results = await provider.send(recipient=actors, message="hi", subject="s")

    assert len(provider.send_calls) == 2  # one call per recipient
    assert len(results) == 1  # Bob's exception was swallowed, not appended
    assert len(provider.sent_calls) == 2  # __sent__ still called for both


async def test_email_hooks_batch(actors):
    """batch_recipients=True: _send_ once with the full list; __sent__ once."""
    provider = _DummyMailProvider()
    provider.batch_recipients = True

    results = await provider.send(recipient=actors, message="hi", subject="s")

    assert len(provider.send_calls) == 1
    called_to, _, _ = provider.send_calls[0]
    assert called_to == actors
    assert len(results) == 1
    assert len(provider.sent_calls) == 1
    sent_recipient, _, _, _ = provider.sent_calls[0]
    assert sent_recipient == actors


async def test_email_hooks_raise_errors_on_connect():
    provider = _DummyMailProvider()
    provider.raise_errors = (ValueError,)
    provider.connect_error = ValueError("bad credentials")

    with pytest.raises(ValueError):
        await provider.send(recipient=[], message="hi", subject="s")


async def test_email_hooks_raise_errors_on_send(actors):
    provider = _DummyMailProvider()
    provider.raise_errors = (ValueError,)
    provider.batch_recipients = True
    provider.send_error = ValueError("permission denied")

    with pytest.raises(ValueError):
        await provider.send(recipient=actors, message="hi", subject="s")


async def test_email_hooks_connect_error_wrapped_by_default():
    """Without raise_errors, a connect() failure is still wrapped in ProviderError."""
    provider = _DummyMailProvider()
    provider.connect_error = RuntimeError("smtp down")

    with pytest.raises(ProviderError):
        await provider.send(recipient=[], message="hi", subject="s")


async def test_email_hooks_redacted_kwargs(actors):
    provider = _DummyMailProvider()
    provider.batch_recipients = True
    provider.redacted_send_kwargs = frozenset({"user_assertion"})

    await provider.send(
        recipient=actors, message="hi", subject="s", user_assertion="super-secret-token", cc=["x@y.com"]
    )

    assert len(provider.sent_calls) == 1
    _, _, _, callback_kwargs = provider.sent_calls[0]
    assert "user_assertion" not in callback_kwargs
    assert callback_kwargs.get("cc") == ["x@y.com"]
    # the _send_ call itself still receives the full kwargs, unredacted
    _, _, send_kwargs = provider.send_calls[0]
    assert send_kwargs.get("user_assertion") == "super-secret-token"
