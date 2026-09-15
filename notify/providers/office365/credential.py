"""MSAL-backed asynchronous credential for Microsoft Graph.

Implements the ``azure.core.credentials_async.AsyncTokenCredential`` protocol
for all four supported auth flows (client credentials, on-behalf-of,
delegated, and the deprecated password/ROPC flow) on top of one MSAL
``SerializableTokenCache``, persisted through a pluggable
``notify.providers.office365.token_store.TokenStore``.

MSAL itself is synchronous, so every MSAL call runs in the default executor
via ``loop.run_in_executor``. Graph calls made by ``msgraph-sdk`` stay fully
async and reach this module only through Kiota's
``get_token(*scopes, claims=..., enable_cae=...)`` calls.
"""
import asyncio
import time
import warnings
from contextlib import contextmanager
from contextvars import ContextVar
from enum import Enum
from typing import Any, Iterator, Optional

import msal
from azure.core.credentials import AccessToken
from navconfig.logging import logging

from notify.exceptions import NotifyAuthError
from notify.providers._msgraph import GRAPH_DEFAULT_SCOPE
from notify.providers.office365.token_store import TokenStore


logger = logging.getLogger(__name__)


class AuthFlow(str, Enum):
    """The four Microsoft Graph auth flows this provider supports."""

    CLIENT_CREDENTIALS = "client_credentials"
    ON_BEHALF_OF = "on_behalf_of"
    DELEGATED = "delegated"
    PASSWORD = "password"


#: Delegated scopes (Mail.Send + Mail.Send.Shared); every other flow uses
#: the Graph ``.default`` scope.
DELEGATED_SCOPES: tuple[str, ...] = (
    "https://graph.microsoft.com/Mail.Send",
    "https://graph.microsoft.com/Mail.Send.Shared",
)

#: Module-level context var carrying the OBO user assertion for the
#: duration of a `use_assertion(...)` block. Scoped per asyncio Task, so
#: concurrent sends for different users never mix assertions.
_current_assertion: ContextVar[Optional[str]] = ContextVar("_o365_user_assertion", default=None)


def scopes_for(flow: AuthFlow) -> list[str]:
    """Return the Graph scopes to request for a given auth flow.

    Args:
        flow: The configured auth flow.

    Returns:
        `[GRAPH_DEFAULT_SCOPE]` for `client_credentials` / `on_behalf_of` /
        `password`; `DELEGATED_SCOPES` for `delegated`.
    """
    if flow == AuthFlow.DELEGATED:
        return list(DELEGATED_SCOPES)
    return [GRAPH_DEFAULT_SCOPE]


def _load_certificate_credential(
    path: str, thumbprint: Optional[str], passphrase: Optional[str]
) -> dict:
    """Build the MSAL certificate `client_credential` dict from a PEM file on disk."""
    with open(path, "r", encoding="utf-8") as fh:
        private_key = fh.read()
    credential = {"private_key": private_key, "thumbprint": thumbprint}
    if passphrase:
        credential["passphrase"] = passphrase
    return credential


def _describe_msal_error(result: dict) -> str:
    """Render an MSAL error dict into a message with no secrets, tokens or assertions."""
    message = f"O365 Graph authentication failed: {result.get('error', 'unknown_error')}"
    description = result.get("error_description")
    if description:
        message += f" — {description}"
    correlation_id = result.get("correlation_id")
    if correlation_id:
        message += f" (correlation_id={correlation_id})"
    return message


class MsalAsyncCredential:
    """AsyncTokenCredential backed by MSAL with a pluggable token cache."""

    def __init__(
        self,
        *,
        flow: AuthFlow,
        tenant_id: str,
        client_id: str,
        client_secret: Optional[str] = None,
        client_certificate_path: Optional[str] = None,
        client_certificate_thumbprint: Optional[str] = None,
        client_certificate_password: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        token_store: TokenStore,
        authority_host: str = "https://login.microsoftonline.com",
    ) -> None:
        """Validate inputs for `flow` and prepare (but do not build) the MSAL app.

        Building the actual `msal.ClientApplication` is deferred to the first
        `get_token` / `initiate_device_flow` call (via the executor): MSAL's
        authority initialization performs OIDC tenant discovery over HTTP, so
        constructing it here would make this constructor — and therefore
        `Office365.connect()` — perform a network call.

        Raises:
            NotifyAuthError: When a required input for `flow` is missing.
        """
        self._flow = AuthFlow(flow)
        if not client_id:
            raise NotifyAuthError("O365 credential requires client_id.")
        if not tenant_id:
            raise NotifyAuthError("O365 credential requires tenant_id.")

        self._tenant_id = tenant_id
        self._client_id = client_id
        self._username = username
        self._password = password
        self._token_store = token_store
        self._authority = f"{authority_host.rstrip('/')}/{tenant_id}"
        self._cache_key = f"{tenant_id}:{client_id}:{self._flow.value}"
        self._cache = msal.SerializableTokenCache()
        self._cache_loaded = False
        self._lock = asyncio.Lock()
        self._password_warned = False
        self._app: Optional[Any] = None

        client_credential = None
        if client_secret:
            client_credential = client_secret
        elif client_certificate_path:
            client_credential = _load_certificate_credential(
                client_certificate_path, client_certificate_thumbprint, client_certificate_password
            )

        if self._flow in (AuthFlow.CLIENT_CREDENTIALS, AuthFlow.ON_BEHALF_OF):
            if not client_credential:
                raise NotifyAuthError(
                    f"O365 auth_flow={self._flow.value} requires client_secret or client_certificate_path."
                )
        elif self._flow == AuthFlow.PASSWORD:
            if not username or not password:
                raise NotifyAuthError("O365 auth_flow=password requires username and password.")
        elif self._flow != AuthFlow.DELEGATED:  # pragma: no cover - AuthFlow(flow) already validates membership
            raise NotifyAuthError(f"Unknown O365 auth flow: {flow!r}")

        self._client_credential = client_credential

    def _build_app(self) -> Any:
        """Synchronously construct the MSAL `ClientApplication` (runs in the executor).

        This is where MSAL performs its OIDC tenant discovery HTTP call, so it
        must never run directly on the event loop.
        """
        if self._flow in (AuthFlow.CLIENT_CREDENTIALS, AuthFlow.ON_BEHALF_OF):
            return msal.ConfidentialClientApplication(
                self._client_id,
                client_credential=self._client_credential,
                authority=self._authority,
                token_cache=self._cache,
            )
        if self._flow == AuthFlow.DELEGATED:
            return msal.PublicClientApplication(
                self._client_id, authority=self._authority, token_cache=self._cache
            )
        # AuthFlow.PASSWORD
        if self._client_credential:
            return msal.ConfidentialClientApplication(
                self._client_id,
                client_credential=self._client_credential,
                authority=self._authority,
                token_cache=self._cache,
            )
        return msal.PublicClientApplication(
            self._client_id, authority=self._authority, token_cache=self._cache
        )

    async def _ensure_app(self) -> Any:
        """Lazily build the MSAL application, once, under the async lock."""
        if self._app is not None:
            return self._app
        async with self._lock:
            if self._app is None:
                loop = asyncio.get_running_loop()
                self._app = await loop.run_in_executor(None, self._build_app)
        return self._app

    async def _ensure_cache_loaded(self) -> None:
        """Load the serialized cache from the token store, once, lazily."""
        if self._cache_loaded:
            return
        async with self._lock:
            if self._cache_loaded:
                return
            serialized = await self._token_store.load(self._cache_key)
            if serialized:
                self._cache.deserialize(serialized)
            self._cache_loaded = True

    async def _persist_cache_if_changed(self) -> None:
        """Persist the cache only when MSAL reports it changed, under the async lock."""
        if not self._cache.has_state_changed:
            return
        async with self._lock:
            if self._cache.has_state_changed:
                await self._token_store.save(self._cache_key, self._cache.serialize())

    def _match_account(self, accounts: list[dict]) -> Optional[dict]:
        if not accounts:
            return None
        if self._username:
            target = self._username.lower()
            for account in accounts:
                if (account.get("username") or "").lower() == target:
                    return account
            return None
        return accounts[0]

    @staticmethod
    def _raise_for_error(result: Optional[dict]) -> dict:
        if not result:
            raise NotifyAuthError("O365 Graph authentication failed: MSAL returned no result.")
        if "error" in result:
            raise NotifyAuthError(_describe_msal_error(result))
        return result

    @staticmethod
    def _to_access_token(result: dict) -> AccessToken:
        expires_on = result.get("expires_on")
        if expires_on is None:
            expires_on = int(time.time()) + int(result.get("expires_in") or 0)
        return AccessToken(result["access_token"], int(expires_on))

    async def get_token(
        self,
        *scopes: str,
        claims: Optional[str] = None,
        tenant_id: Optional[str] = None,
        enable_cae: bool = False,
        **kwargs: Any,
    ) -> AccessToken:
        """Return a cache-first `AccessToken` for the configured flow.

        Args:
            scopes: Scopes requested by Kiota; falls back to `scopes_for(flow)`
                when empty.
            claims: Passed to MSAL as `claims_challenge`.
            tenant_id: Unused (this credential is bound to one tenant at
                construction); accepted for protocol compatibility.
            enable_cae: Accepted and ignored (protocol compatibility).

        Returns:
            AccessToken: `(token, expires_on)`.

        Raises:
            NotifyAuthError: On any MSAL failure, a missing OBO assertion, or
                a delegated flow with no usable cached account.
        """
        await self._ensure_cache_loaded()
        app = await self._ensure_app()
        loop = asyncio.get_running_loop()
        requested_scopes = list(scopes) if scopes else scopes_for(self._flow)

        if self._flow == AuthFlow.CLIENT_CREDENTIALS:
            result = await loop.run_in_executor(
                None,
                lambda: app.acquire_token_for_client(requested_scopes, claims_challenge=claims),
            )
        elif self._flow == AuthFlow.ON_BEHALF_OF:
            assertion = _current_assertion.get()
            if not assertion:
                raise NotifyAuthError(
                    "on_behalf_of auth flow requires a user assertion bound via "
                    "MsalAsyncCredential.use_assertion(...) / send(user_assertion=...)."
                )
            result = await loop.run_in_executor(
                None,
                lambda: app.acquire_token_on_behalf_of(
                    assertion, requested_scopes, claims_challenge=claims
                ),
            )
        elif self._flow == AuthFlow.DELEGATED:
            accounts = await loop.run_in_executor(None, app.get_accounts)
            account = self._match_account(accounts)
            if account is None:
                raise NotifyAuthError(
                    "No cached delegated O365 account found; run: "
                    "python -m notify.providers.office365.login --username <user>"
                )
            result = await loop.run_in_executor(
                None,
                lambda: app.acquire_token_silent(
                    requested_scopes, account=account, claims_challenge=claims
                ),
            )
            if not result:
                raise NotifyAuthError(
                    "Cached O365 delegated token could not be refreshed silently; run: "
                    "python -m notify.providers.office365.login --username <user>"
                )
        elif self._flow == AuthFlow.PASSWORD:
            if not self._password_warned:
                warnings.warn(
                    "O365 auth_flow='password' (ROPC) is deprecated; use 'delegated' "
                    "(device-code login) or 'on_behalf_of' instead.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                self._password_warned = True
            result = await loop.run_in_executor(
                None,
                lambda: app.acquire_token_by_username_password(
                    self._username, self._password, requested_scopes, claims_challenge=claims
                ),
            )
        else:  # pragma: no cover - AuthFlow(flow) already validates membership
            raise NotifyAuthError(f"Unknown O365 auth flow: {self._flow!r}")

        result = self._raise_for_error(result)
        await self._persist_cache_if_changed()
        return self._to_access_token(result)

    @contextmanager
    def use_assertion(self, user_assertion: str) -> Iterator[None]:
        """Bind a user assertion to the current asyncio context for OBO `get_token` calls.

        Args:
            user_assertion: The signed-in user's Graph-audience bearer token.
        """
        token = _current_assertion.set(user_assertion)
        try:
            yield
        finally:
            _current_assertion.reset(token)

    async def initiate_device_flow(self, scopes: Optional[list[str]] = None) -> dict:
        """Start a device-code flow (delegated only).

        Returns:
            dict: MSAL's flow dict (`user_code`, `message`, `device_code`, ...).

        Raises:
            NotifyAuthError: If this credential is not `delegated`, or MSAL
                could not start the flow.
        """
        if self._flow != AuthFlow.DELEGATED:
            raise NotifyAuthError("Device-code flow is only available for auth_flow='delegated'.")
        app = await self._ensure_app()
        loop = asyncio.get_running_loop()
        requested_scopes = scopes or scopes_for(self._flow)
        flow = await loop.run_in_executor(
            None, lambda: app.initiate_device_flow(scopes=requested_scopes)
        )
        if "user_code" not in flow:
            raise NotifyAuthError(
                f"Failed to start O365 device-code flow: "
                f"{flow.get('error_description') or flow.get('error') or 'unknown error'}"
            )
        return flow

    async def complete_device_flow(self, flow: dict) -> None:
        """Block (in the executor) until the user signs in; persists the cache.

        Args:
            flow: The dict returned by `initiate_device_flow`.

        Raises:
            NotifyAuthError: On any MSAL failure (including a device-code timeout).
        """
        await self._ensure_cache_loaded()
        app = await self._ensure_app()
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, lambda: app.acquire_token_by_device_flow(flow))
        self._raise_for_error(result)
        await self._persist_cache_if_changed()

    async def close(self) -> None:
        """Persist a changed cache and close the token store."""
        await self._persist_cache_if_changed()
        await self._token_store.close()

    async def __aenter__(self) -> "MsalAsyncCredential":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()
