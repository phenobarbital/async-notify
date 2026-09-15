"""Offline tests for the Outlook Graph alias (FEAT-004, M7).

`Outlook` is a subclass of the Graph-based `Office365` provider; the
legacy `office365.graph_client.GraphClient` / `acquire_token*` REST-client
behavior no longer exists.
"""

import sys
from unittest.mock import AsyncMock, patch

import pytest

from notify.providers.office365.office365 import Office365
from notify.providers.outlook import Outlook


@pytest.fixture
async def outlook() -> Outlook:
    return Outlook(client_id="test_client_id", client_secret="test_client_secret", tenant_id="test_tenant_id")


async def test_outlook_is_office365_subclass(outlook):
    assert isinstance(outlook, Office365)
    assert outlook.provider == "outlook"


async def test_context_methods(outlook):
    with (
        patch.object(outlook, "connect", new_callable=AsyncMock) as mock_connect,
        patch.object(outlook, "close", new_callable=AsyncMock) as mock_close,
    ):
        async with outlook:
            mock_connect.assert_called_once()
        mock_close.assert_called_once()


async def test_connect_builds_graph_client_no_network(outlook):
    assert outlook._graph is None
    await outlook.connect()
    assert outlook._graph is not None
    assert outlook._credential is not None
    assert outlook._credential._app is None  # MSAL app construction stays deferred
    await outlook.close()
    assert outlook._graph is None


async def test_required_variables_on_connect(outlook):
    for var in ("client_id", "client_secret", "tenant_id"):
        assert getattr(outlook, var) is not None


async def test_legacy_rest_methods_removed(outlook):
    assert not hasattr(outlook, "acquire_token")
    assert not hasattr(outlook, "acquire_token_by_username")


async def test_no_legacy_rest_libraries_imported():
    # Importing notify.providers.outlook must never pull in the broken
    # Office365-REST-Python-Client (office365.graph_client) or the O365 package.
    assert "office365.graph_client" not in sys.modules
    assert "O365" not in sys.modules


async def test_add_attachment_queues_and_missing_path_raises(tmp_path, outlook):
    with pytest.raises(FileNotFoundError):
        await outlook.add_attachment(str(tmp_path / "missing.txt"))
    assert outlook._pending_attachments == []

    file_path = tmp_path / "report.txt"
    file_path.write_text("hello", encoding="utf-8")
    await outlook.add_attachment(str(file_path))
    assert outlook._pending_attachments == [file_path]


async def test_send_merges_and_clears_queued_attachments(monkeypatch, tmp_path, outlook):
    file_path = tmp_path / "report.txt"
    file_path.write_text("hello", encoding="utf-8")
    await outlook.add_attachment(str(file_path))

    captured = {}

    async def fake_office365_send(self, to, message, subject=None, **kwargs):
        captured["attachments"] = kwargs.get("attachments")
        return "sent"

    monkeypatch.setattr(Office365, "_send_", fake_office365_send)

    result = await outlook._send_([], "hi", subject="s")
    assert result == "sent"
    assert captured["attachments"] == [file_path]
    assert outlook._pending_attachments == []

    # A second send with nothing newly queued gets no attachments merged in.
    captured.clear()
    await outlook._send_([], "hi", subject="s")
    assert captured.get("attachments") is None


async def test_queue_cleared_even_on_send_failure(monkeypatch, tmp_path, outlook):
    file_path = tmp_path / "x.txt"
    file_path.write_text("y", encoding="utf-8")
    await outlook.add_attachment(str(file_path))

    async def failing_send(self, to, message, subject=None, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(Office365, "_send_", failing_send)

    with pytest.raises(RuntimeError):
        await outlook._send_([], "hi", subject="s")
    assert outlook._pending_attachments == []
