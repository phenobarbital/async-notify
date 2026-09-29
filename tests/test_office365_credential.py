"""Offline tests for the MSAL-backed async Graph credential (FEAT-004, M3)."""

import asyncio

import pytest

from notify.exceptions import NotifyAuthError
from notify.providers.office365 import credential as credential_module
from notify.providers.office365.credential import AuthFlow, MsalAsyncCredential, scopes_for
from notify.providers.office365.token_store import MemoryTokenStore


class _FakeConfidentialClientApplication:
    """Records constructor args and returns a canned MSAL result dict."""

    last_instance = None

    def __init__(self, client_id, client_credential=None, authority=None, token_cache=None):
        self.client_id = client_id
        self.client_credential = client_credential
        self.authority = authority
        self.token_cache = token_cache
        self.acquire_token_for_client_calls = []
        self.acquire_token_on_behalf_of_calls = []
        self.acquire_token_by_username_password_calls = []
        type(self).last_instance = self

    def acquire_token_for_client(self, scopes, claims_challenge=None, **kwargs):
        self.acquire_token_for_client_calls.append((scopes, claims_challenge))
        return {"access_token": "app-only-token", "expires_in": 3600}

    def acquire_token_on_behalf_of(self, user_assertion, scopes, claims_challenge=None, **kwargs):
        self.acquire_token_on_behalf_of_calls.append((user_assertion, scopes, claims_challenge))
        return {"access_token": f"obo-token-for-{user_assertion}", "expires_in": 3600}

    def acquire_token_by_username_password(self, username, password, scopes, claims_challenge=None, **kwargs):
        self.acquire_token_by_username_password_calls.append((username, password, scopes))
        return {"access_token": "ropc-token", "expires_in": 3600}


class _FakePublicClientApplication:
    last_instance = None

    def __init__(self, client_id, authority=None, token_cache=None):
        self.client_id = client_id
        self.authority = authority
        self.token_cache = token_cache
        self._accounts = []
        type(self).last_instance = self

    def get_accounts(self, username=None):
        return self._accounts

    def acquire_token_silent(self, scopes, account=None, claims_challenge=None, **kwargs):
        return {"access_token": "delegated-token", "expires_in": 3600}

    def initiate_device_flow(self, scopes=None, **kwargs):
        return {"user_code": "ABC123", "message": "go sign in", "device_code": "dc"}

    def acquire_token_by_device_flow(self, flow, **kwargs):
        return {"access_token": "device-token", "expires_in": 3600}

    def acquire_token_by_username_password(self, username, password, scopes, claims_challenge=None, **kwargs):
        return {"access_token": "ropc-public-token", "expires_in": 3600}


@pytest.fixture(autouse=True)
def msal_apps(monkeypatch):
    monkeypatch.setattr(credential_module.msal, "ConfidentialClientApplication", _FakeConfidentialClientApplication)
    monkeypatch.setattr(credential_module.msal, "PublicClientApplication", _FakePublicClientApplication)
    yield


def _cca() -> MsalAsyncCredential:
    return MsalAsyncCredential(
        flow=AuthFlow.CLIENT_CREDENTIALS,
        tenant_id="tenant-1",
        client_id="client-1",
        client_secret="s3cr3t",
        token_store=MemoryTokenStore(),
    )


async def test_credential_client_credentials_secret():
    cred = _cca()
    token = await cred.get_token("https://graph.microsoft.com/.default")
    assert token.token == "app-only-token"
    assert token.expires_on > 0


async def test_credential_client_credentials_certificate(tmp_path):
    cert_path = tmp_path / "cert.pem"
    cert_path.write_text("-----BEGIN PRIVATE KEY-----\nFAKE\n-----END PRIVATE KEY-----\n", encoding="utf-8")

    cred = MsalAsyncCredential(
        flow=AuthFlow.CLIENT_CREDENTIALS,
        tenant_id="tenant-1",
        client_id="client-1",
        client_certificate_path=str(cert_path),
        client_certificate_thumbprint="ABCDEF",
        token_store=MemoryTokenStore(),
    )
    await cred.get_token()
    app = _FakeConfidentialClientApplication.last_instance
    assert isinstance(app.client_credential, dict)
    assert app.client_credential["thumbprint"] == "ABCDEF"
    assert "FAKE" in app.client_credential["private_key"]


async def test_credential_obo_requires_assertion():
    cred = MsalAsyncCredential(
        flow=AuthFlow.ON_BEHALF_OF,
        tenant_id="tenant-1",
        client_id="client-1",
        client_secret="s3cr3t",
        token_store=MemoryTokenStore(),
    )
    with pytest.raises(NotifyAuthError):
        await cred.get_token()


async def test_credential_obo_contexts_isolated():
    cred = MsalAsyncCredential(
        flow=AuthFlow.ON_BEHALF_OF,
        tenant_id="tenant-1",
        client_id="client-1",
        client_secret="s3cr3t",
        token_store=MemoryTokenStore(),
    )

    async def _send_as(assertion: str) -> str:
        with cred.use_assertion(assertion):
            await asyncio.sleep(0)  # yield control, simulating concurrent I/O
            token = await cred.get_token()
            return token.token

    results = await asyncio.gather(_send_as("user-a-token"), _send_as("user-b-token"))
    assert set(results) == {"obo-token-for-user-a-token", "obo-token-for-user-b-token"}


async def test_credential_delegated_without_account_hints_login():
    cred = MsalAsyncCredential(
        flow=AuthFlow.DELEGATED,
        tenant_id="tenant-1",
        client_id="client-1",
        username="me@contoso.com",
        token_store=MemoryTokenStore(),
    )
    with pytest.raises(NotifyAuthError) as excinfo:
        await cred.get_token()
    assert "notify.providers.office365.login" in str(excinfo.value)


async def test_credential_password_warns():
    cred = MsalAsyncCredential(
        flow=AuthFlow.PASSWORD,
        tenant_id="tenant-1",
        client_id="client-1",
        username="me@contoso.com",
        password="p@ss",
        token_store=MemoryTokenStore(),
    )
    with pytest.warns(DeprecationWarning):
        await cred.get_token()


async def test_credential_persists_only_on_change():
    """`_persist_cache_if_changed` saves only when MSAL's `has_state_changed` is
    True (real MSAL flips this on real cache mutation; the fake app used in
    these tests does not touch the cache, so we drive the flag directly)."""
    store = MemoryTokenStore()
    cred = _cca()
    cred._token_store = store

    saved_calls = []
    original_save = store.save

    async def _tracking_save(key, value):
        saved_calls.append((key, value))
        await original_save(key, value)

    store.save = _tracking_save

    # No cache mutation yet: get_token must not trigger a save.
    await cred.get_token()
    assert saved_calls == []

    # Simulate MSAL having written a new/refreshed token into the cache.
    cred._cache.has_state_changed = True
    await cred._persist_cache_if_changed()
    assert len(saved_calls) == 1
    assert cred._cache.has_state_changed is False  # serialize() resets the flag

    # Calling again with nothing changed must not save a second time.
    await cred._persist_cache_if_changed()
    assert len(saved_calls) == 1


async def test_credential_error_never_leaks_secrets():
    """The OBO assertion and the configured client_secret never appear in the
    exception text (only MSAL's own error/error_description/correlation_id
    fields are surfaced, which never include the assertion or the secret)."""
    secret = "super-secret-client-value"
    assertion = "user-bearer-assertion-value"

    class _FailingCCA(_FakeConfidentialClientApplication):
        def acquire_token_on_behalf_of(self, user_assertion, scopes, claims_challenge=None, **kwargs):
            return {
                "error": "invalid_grant",
                "error_description": "AADSTS50013: Assertion is invalid.",
                "correlation_id": "corr-123",
            }

    cred = MsalAsyncCredential(
        flow=AuthFlow.ON_BEHALF_OF,
        tenant_id="tenant-1",
        client_id="client-1",
        client_secret=secret,
        token_store=MemoryTokenStore(),
    )
    cred._app = _FailingCCA("client-1", client_credential=secret)

    with cred.use_assertion(assertion):
        with pytest.raises(NotifyAuthError) as excinfo:
            await cred.get_token()

    message = str(excinfo.value)
    assert "invalid_grant" in message
    assert "corr-123" in message
    assert secret not in message
    assert assertion not in message


def test_scopes_for_delegated_vs_default():
    assert scopes_for(AuthFlow.DELEGATED) == list(credential_module.DELEGATED_SCOPES)
    assert scopes_for(AuthFlow.CLIENT_CREDENTIALS) == [credential_module.GRAPH_DEFAULT_SCOPE]
    assert scopes_for(AuthFlow.ON_BEHALF_OF) == [credential_module.GRAPH_DEFAULT_SCOPE]
    assert scopes_for(AuthFlow.PASSWORD) == [credential_module.GRAPH_DEFAULT_SCOPE]


def test_missing_required_inputs_raise():
    with pytest.raises(NotifyAuthError):
        MsalAsyncCredential(
            flow=AuthFlow.CLIENT_CREDENTIALS,
            tenant_id="tenant-1",
            client_id="client-1",
            token_store=MemoryTokenStore(),
        )
    with pytest.raises(NotifyAuthError):
        MsalAsyncCredential(
            flow=AuthFlow.CLIENT_CREDENTIALS,
            tenant_id="",
            client_id="client-1",
            client_secret="s3cr3t",
            token_store=MemoryTokenStore(),
        )
