"""Offline tests for the notify-server OBO-assertion queue guard (FEAT-004, M10).

An OBO `user_assertion` is a live user token and must never reach Redis,
cloudpickle, or a TCP payload. `reject_queued_secrets()` runs as the first
statement of `NotifyWrapper.__init__` and of `NotifyClient.publish` /
`stream` / `send`, so a forbidden key is caught before any serialization
or network call.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from notify.exceptions import MessageError
from notify.server.client import NotifyClient
from notify.server.wrapper import QUEUE_FORBIDDEN_KWARGS, NotifyWrapper, reject_queued_secrets


def test_queue_forbidden_kwargs_contains_user_assertion():
    assert QUEUE_FORBIDDEN_KWARGS == frozenset({"user_assertion"})


def test_reject_queued_secrets_top_level_key():
    with pytest.raises(MessageError) as excinfo:
        reject_queued_secrets({"user_assertion": "super-secret-token", "subject": "hi"})
    message = str(excinfo.value)
    assert "user_assertion" in message
    assert "super-secret-token" not in message


def test_reject_queued_secrets_nested_kwargs_key():
    with pytest.raises(MessageError) as excinfo:
        reject_queued_secrets({"provider": "office365", "kwargs": {"user_assertion": "super-secret-token"}})
    message = str(excinfo.value)
    assert "user_assertion" in message
    assert "super-secret-token" not in message


def test_reject_queued_secrets_allows_clean_message():
    reject_queued_secrets({"subject": "hi", "kwargs": {"cc": ["a@b.com"]}})  # no exception


def test_notify_wrapper_construction_rejects_assertion():
    with pytest.raises(MessageError) as excinfo:
        NotifyWrapper("office365", user_assertion="super-secret-token")
    assert "super-secret-token" not in str(excinfo.value)


def test_notify_wrapper_allows_normal_kwargs():
    wrapper = NotifyWrapper("office365", subject="hi")
    assert wrapper._provider == "office365"


@pytest.fixture
def client() -> NotifyClient:
    return NotifyClient(redis_url="redis://localhost:6379/0")


async def test_client_publish_rejects_before_redis(client):
    client.redis = MagicMock()
    client.redis.publish = AsyncMock()
    with pytest.raises(MessageError):
        await client.publish({"user_assertion": "token"}, "channel")
    client.redis.publish.assert_not_called()


async def test_client_stream_rejects_before_redis(client):
    client.redis = MagicMock()
    client.redis.xadd = AsyncMock()
    with pytest.raises(MessageError):
        await client.stream({"user_assertion": "token"}, "stream")
    client.redis.xadd.assert_not_called()


async def test_client_stream_wrapper_shape_rejects_before_redis(client):
    client.redis = MagicMock()
    client.redis.xadd = AsyncMock()
    with pytest.raises(MessageError):
        await client.stream({"provider": "office365", "user_assertion": "token"}, "stream", use_wrapper=True)
    client.redis.xadd.assert_not_called()


async def test_client_send_rejects_before_tcp(client):
    with patch("asyncio.open_connection", new=AsyncMock()) as mock_open:
        with pytest.raises(MessageError):
            await client.send({"user_assertion": "token"})
        mock_open.assert_not_called()


async def test_client_publish_allows_clean_message(client):
    client.redis = MagicMock()
    client.redis.publish = AsyncMock()
    await client.publish({"subject": "hi"}, "channel")
    client.redis.publish.assert_called_once()
