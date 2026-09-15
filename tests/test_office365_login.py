"""Offline tests for the Office365 device-code login CLI (FEAT-004, M8)."""

import pytest

from notify.exceptions import NotifyAuthError
from notify.providers.office365 import login as login_module
from notify.providers.office365.token_store import MemoryTokenStore


def test_login_cli_refuses_memory_store(capsys):
    exit_code = login_module.main(["--username", "me@contoso.com", "--token-store", "memory"])
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "memory" in captured.err.lower()


def test_login_cli_requires_tenant_id(monkeypatch, capsys):
    monkeypatch.setattr(login_module, "O365_TENANT_ID", None)
    exit_code = login_module.main(["--username", "me@contoso.com", "--client-id", "c", "--token-store", "file"])
    assert exit_code == 2
    assert "tenant" in capsys.readouterr().err.lower()


def test_login_cli_requires_client_id(monkeypatch, capsys):
    monkeypatch.setattr(login_module, "O365_CLIENT_ID", None)
    exit_code = login_module.main(["--username", "me@contoso.com", "--tenant-id", "t", "--token-store", "file"])
    assert exit_code == 2
    assert "client" in capsys.readouterr().err.lower()


def test_login_cli_missing_username_is_argparse_error(capsys):
    with pytest.raises(SystemExit) as excinfo:
        login_module.main(["--tenant-id", "t", "--client-id", "c"])
    assert excinfo.value.code == 2


def test_login_cli_success_persists_cache(monkeypatch, capsys):
    saved = {}

    async def fake_device_code_login(*, username, tenant_id, client_id, token_store):
        saved["username"] = username
        saved["tenant_id"] = tenant_id
        saved["client_id"] = client_id
        await token_store.save("tenant:client:delegated", "fake-cache-blob")

    monkeypatch.setattr(login_module, "device_code_login", fake_device_code_login)
    monkeypatch.setattr(login_module, "build_token_store", lambda kind: MemoryTokenStore())

    exit_code = login_module.main(
        ["--username", "me@contoso.com", "--tenant-id", "t", "--client-id", "c", "--token-store", "file"]
    )

    assert exit_code == 0
    assert saved["username"] == "me@contoso.com"
    captured = capsys.readouterr()
    assert "succeeded" in captured.err.lower()


def test_login_cli_auth_error_exits_1(monkeypatch, capsys):
    async def failing_device_code_login(**kwargs):
        raise NotifyAuthError("device code timed out")

    monkeypatch.setattr(login_module, "device_code_login", failing_device_code_login)
    monkeypatch.setattr(login_module, "build_token_store", lambda kind: MemoryTokenStore())

    exit_code = login_module.main(
        ["--username", "me@contoso.com", "--tenant-id", "t", "--client-id", "c", "--token-store", "file"]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "device code timed out" in captured.err


async def test_device_code_login_runs_full_flow(monkeypatch):
    class _FakeCredential:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.closed = False

        async def initiate_device_flow(self):
            return {"user_code": "ABC123", "message": "Go to https://microsoft.com/devicelogin"}

        async def complete_device_flow(self, flow):
            assert flow["user_code"] == "ABC123"

        async def close(self):
            self.closed = True

    created = {}

    def _fake_credential_factory(**kwargs):
        cred = _FakeCredential(**kwargs)
        created["credential"] = cred
        return cred

    monkeypatch.setattr(login_module, "MsalAsyncCredential", _fake_credential_factory)

    store = MemoryTokenStore()
    await login_module.device_code_login(username="me@contoso.com", tenant_id="t", client_id="c", token_store=store)

    assert created["credential"].closed is True


async def test_device_code_login_propagates_auth_error(monkeypatch):
    class _FailingCredential:
        def __init__(self, **kwargs):
            pass

        async def initiate_device_flow(self):
            raise NotifyAuthError("could not start device flow")

        async def complete_device_flow(self, flow):
            raise AssertionError("should not be reached")

        async def close(self):
            pass

    monkeypatch.setattr(login_module, "MsalAsyncCredential", _FailingCredential)

    with pytest.raises(NotifyAuthError):
        await login_module.device_code_login(
            username="me@contoso.com", tenant_id="t", client_id="c", token_store=MemoryTokenStore()
        )
