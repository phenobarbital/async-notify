# -*- coding: utf-8 -*-
"""Office 365 Email provider — Microsoft Graph email (send-as & On-Behalf-Of).

Rewritten on `msgraph-sdk` (see FEAT-004): a single MSAL-backed async
credential fronts all four Graph auth flows (client credentials, on-behalf-of,
delegated, and the deprecated password/ROPC flow), and a `GraphServiceClient`
handles Graph HTTP.

This module implements the provider's *lifecycle* (constructor, flow
resolution, `connect()`/`close()`). Rendering and message dispatch
(`_render_`/`_send_`) are implemented alongside this (see TASK-27).
"""
import warnings
from typing import Optional, Union

from msgraph import GraphServiceClient

from notify.conf import (
    O365_AUTH_FLOW,
    O365_CLIENT_CERTIFICATE_PASSWORD,
    O365_CLIENT_CERTIFICATE_PATH,
    O365_CLIENT_CERTIFICATE_THUMBPRINT,
    O365_CLIENT_ID,
    O365_CLIENT_SECRET,
    O365_PASSWORD,
    O365_SENDER,
    O365_TENANT_ID,
    O365_USER,
)
from notify.exceptions import NotifyAuthError, ProviderError
from notify.providers._msgraph import patch_graph_host_os_header
from notify.providers.mail import ProviderEmail
from notify.providers.office365.credential import AuthFlow, MsalAsyncCredential, scopes_for
from notify.providers.office365.token_store import TokenStore, build_token_store


# Sanitise msgraph-core's HostOs telemetry header before the first Graph
# request, same as notify/providers/teams/teams.py:57.
patch_graph_host_os_header()


class Office365(ProviderEmail):
    """Microsoft Graph email provider (app-only, On-Behalf-Of, delegated, legacy ROPC).

    Sends one message to all recipients through `msgraph-sdk`, with send-as
    routing, CC/BCC/Reply-To, inline CID images and upload-session
    attachments (see `notify.providers.office365.graph_mail`).
    """

    provider = "office365"
    blocking: str = 'asyncio'
    batch_recipients = True
    raise_errors = (NotifyAuthError,)
    redacted_send_kwargs = frozenset({"user_assertion"})

    def __init__(
        self,
        *args,
        auth_flow: Optional[Union[str, AuthFlow]] = None,
        username: str = None,
        password: str = None,
        use_credentials: Optional[bool] = None,
        client_id: str = None,
        client_secret: str = None,
        tenant_id: str = None,
        client_certificate_path: str = None,
        client_certificate_thumbprint: str = None,
        client_certificate_password: str = None,
        sender: str = None,
        token_store: Optional[Union[str, TokenStore]] = None,
        save_to_sent_items: bool = True,
        **kwargs,
    ) -> None:
        """Resolve the auth flow and validate settings.

        Every kwarg this constructor consumes is declared explicitly above,
        so it never reaches `ProviderBase.__init__`'s automatic
        `setattr(self, ...)` for leftover kwargs (base.py:77-81).

        Raises:
            NotifyAuthError: When no auth flow can be resolved from the given
                settings (see the `auth_flow` property / flow-resolution rules).
            ProviderError: When `user_assertion` is passed to the constructor;
                it is a per-`send()` kwarg only (`send(user_assertion=...)`).
        """
        if "user_assertion" in kwargs:
            raise ProviderError(
                "O365 user_assertion is a per-send kwarg (send(user_assertion=...)); "
                "it cannot be passed to the constructor."
            )

        self._graph: Optional[GraphServiceClient] = None
        self._credential: Optional[MsalAsyncCredential] = None
        self._token_store_kind = token_store

        super().__init__(*args, **kwargs)

        self.client_id = client_id if client_id is not None else O365_CLIENT_ID
        self.client_secret = client_secret if client_secret is not None else O365_CLIENT_SECRET
        self.tenant_id = tenant_id if tenant_id is not None else O365_TENANT_ID
        self.client_certificate_path = client_certificate_path or O365_CLIENT_CERTIFICATE_PATH
        self.client_certificate_thumbprint = (
            client_certificate_thumbprint or O365_CLIENT_CERTIFICATE_THUMBPRINT
        )
        # Never a public attribute: keeping it off self avoids leaking it via
        # repr/logging the way ProviderBase's leftover-kwarg setattr would.
        self._client_certificate_password = client_certificate_password or O365_CLIENT_CERTIFICATE_PASSWORD
        self.username = username if username is not None else O365_USER
        self.password = password if password is not None else O365_PASSWORD
        self.use_credentials = use_credentials
        self.sender = sender if sender is not None else O365_SENDER
        self.save_to_sent_items = save_to_sent_items

        self._flow = self._resolve_auth_flow(auth_flow, use_credentials)

    def _resolve_auth_flow(
        self, auth_flow: Optional[Union[str, AuthFlow]], use_credentials: Optional[bool]
    ) -> AuthFlow:
        """Resolve the auth flow, first match wins (spec §3 M6):

        1. the `auth_flow` kwarg
        2. the `O365_AUTH_FLOW` setting
        3. `use_credentials is True` (explicitly passed) -> `password` (warns)
        4. `client_secret` or `client_certificate_path` available -> `client_credentials`
        5. `username` and `password` available -> `password` (warns)
        6. otherwise raise `NotifyAuthError` listing the missing settings

        Raises:
            NotifyAuthError: When no flow can be resolved.
        """
        if auth_flow is not None:
            return AuthFlow(auth_flow)
        if O365_AUTH_FLOW:
            return AuthFlow(O365_AUTH_FLOW)
        if use_credentials is True:
            warnings.warn(
                "O365 use_credentials=True selects the deprecated 'password' (ROPC) auth flow; "
                "pass auth_flow='delegated' or 'client_credentials' instead.",
                DeprecationWarning,
                stacklevel=3,
            )
            return AuthFlow.PASSWORD
        if self.client_secret or self.client_certificate_path:
            return AuthFlow.CLIENT_CREDENTIALS
        if self.username and self.password:
            warnings.warn(
                "O365 resolved the deprecated 'password' (ROPC) auth flow from username/password "
                "with no client_secret/client_certificate_path; pass auth_flow explicitly to silence this.",
                DeprecationWarning,
                stacklevel=3,
            )
            return AuthFlow.PASSWORD
        raise NotifyAuthError(
            "Unable to resolve an O365 auth flow: provide auth_flow (or O365_AUTH_FLOW), "
            "client_secret/client_certificate_path for client_credentials, username/password "
            "for the legacy password flow, or use_credentials=True."
        )

    @property
    def auth_flow(self) -> AuthFlow:
        """The Microsoft Graph auth flow resolved for this instance."""
        return self._flow

    async def connect(self, *args, **kwargs) -> None:
        """Idempotently build the token store, `MsalAsyncCredential` and `GraphServiceClient`.

        Makes no network call: MSAL's own app construction (which performs
        an OIDC network call) is deferred by `MsalAsyncCredential` itself
        until the first token request.
        """
        if self._graph is not None:
            return
        token_store = build_token_store(self._token_store_kind)
        self._credential = MsalAsyncCredential(
            flow=self._flow,
            tenant_id=self.tenant_id,
            client_id=self.client_id,
            client_secret=self.client_secret,
            client_certificate_path=self.client_certificate_path,
            client_certificate_thumbprint=self.client_certificate_thumbprint,
            client_certificate_password=self._client_certificate_password,
            username=self.username,
            password=self.password,
            token_store=token_store,
        )
        self._graph = GraphServiceClient(credentials=self._credential, scopes=scopes_for(self._flow))

    async def close(self) -> None:
        """Persist the token cache and release the Graph client and store."""
        if self._credential is not None:
            await self._credential.close()
        self._graph = None
        self._credential = None
