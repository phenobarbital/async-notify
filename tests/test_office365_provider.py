"""Offline tests for the rewritten Office365 Graph provider lifecycle
(FEAT-004, M6 — constructor, flow resolution, connect()/close()).

Rendering/dispatch (`_render_`/`_send_`) tests are added by TASK-27 in this
same module.
"""
import pytest

from notify.exceptions import NotifyAuthError, ProviderError
from notify.providers.office365.credential import AuthFlow
from notify.providers.office365.office365 import Office365


async def test_flow_resolution_explicit_auth_flow_wins():
    provider = Office365(
        auth_flow="on_behalf_of",
        client_id="c", tenant_id="t", client_secret="s",
        use_credentials=True,  # would otherwise resolve to password
    )
    assert provider.auth_flow == AuthFlow.ON_BEHALF_OF


async def test_flow_resolution_setting_o365_auth_flow(monkeypatch):
    monkeypatch.setattr("notify.providers.office365.office365.O365_AUTH_FLOW", "client_credentials")
    provider = Office365(client_id="c", tenant_id="t", client_secret="s")
    assert provider.auth_flow == AuthFlow.CLIENT_CREDENTIALS


async def test_flow_resolution_use_credentials_true_warns_and_is_password():
    with pytest.warns(DeprecationWarning):
        provider = Office365(client_id="c", tenant_id="t", username="u", password="p", use_credentials=True)
    assert provider.auth_flow == AuthFlow.PASSWORD


async def test_flow_resolution_client_secret_available_is_client_credentials():
    provider = Office365(client_id="c", tenant_id="t", client_secret="s")
    assert provider.auth_flow == AuthFlow.CLIENT_CREDENTIALS


async def test_flow_resolution_client_certificate_available_is_client_credentials():
    provider = Office365(client_id="c", tenant_id="t", client_certificate_path="/tmp/does-not-matter.pem")
    assert provider.auth_flow == AuthFlow.CLIENT_CREDENTIALS


async def test_flow_resolution_username_password_warns_and_is_password(monkeypatch):
    # Force the "no client_secret/certificate available" precondition — this
    # environment's navconfig may otherwise supply a real O365_CLIENT_SECRET.
    monkeypatch.setattr("notify.providers.office365.office365.O365_CLIENT_SECRET", None)
    monkeypatch.setattr("notify.providers.office365.office365.O365_CLIENT_CERTIFICATE_PATH", None)
    with pytest.warns(DeprecationWarning):
        provider = Office365(client_id="c", tenant_id="t", username="u", password="p")
    assert provider.auth_flow == AuthFlow.PASSWORD


async def test_flow_resolution_no_settings_raises(monkeypatch):
    # Force every fallback setting to absent, regardless of this
    # environment's navconfig-configured O365 credentials.
    monkeypatch.setattr("notify.providers.office365.office365.O365_CLIENT_SECRET", None)
    monkeypatch.setattr("notify.providers.office365.office365.O365_CLIENT_CERTIFICATE_PATH", None)
    monkeypatch.setattr("notify.providers.office365.office365.O365_USER", None)
    monkeypatch.setattr("notify.providers.office365.office365.O365_PASSWORD", None)
    monkeypatch.setattr("notify.providers.office365.office365.O365_AUTH_FLOW", None)
    with pytest.raises(NotifyAuthError):
        Office365(client_id="c", tenant_id="t")


async def test_constructor_rejects_user_assertion():
    with pytest.raises(ProviderError):
        Office365(client_id="c", tenant_id="t", client_secret="s", user_assertion="token")


async def test_consumed_kwargs_not_set_on_self():
    provider = Office365(
        client_id="c",
        tenant_id="t",
        client_secret="s",
        client_certificate_password="super-secret-cert-password",
    )
    assert not hasattr(provider, "client_certificate_password")
    # non-secret certificate fields remain accessible for the credential to use
    assert provider.client_id == "c"
    assert provider.client_secret == "s"


async def test_connect_idempotent_no_network():
    provider = Office365(client_id="c", tenant_id="t", client_secret="s")
    await provider.connect()
    graph_first = provider._graph
    credential_first = provider._credential
    await provider.connect()
    assert provider._graph is graph_first
    assert provider._credential is credential_first
    # MSAL's own ClientApplication is never built eagerly by connect()
    assert credential_first._app is None


async def test_close_persists_and_clears_client():
    provider = Office365(client_id="c", tenant_id="t", client_secret="s")
    await provider.connect()
    assert provider._graph is not None
    await provider.close()
    assert provider._graph is None
    assert provider._credential is None
