# -*- coding: utf-8 -*-
"""Office 365 Email provider — Microsoft Graph email (send-as & On-Behalf-Of).

Rewritten on `msgraph-sdk` (see FEAT-004): a single MSAL-backed async
credential fronts all four Graph auth flows (client credentials, on-behalf-of,
delegated, and the deprecated password/ROPC flow), and a `GraphServiceClient`
handles Graph HTTP.

This module implements the provider's lifecycle (constructor, flow
resolution, `connect()`/`close()`) as well as rendering and message dispatch
(`_render_`/`_send_`): one HTML render for the whole recipient list, and one
Graph message sent through `GraphMailSender`, with send-as mailbox routing
and On-Behalf-Of assertion scoping.
"""
import warnings
from typing import Any, Optional, Union

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
from notify.models import Actor, MailSendResult
from notify.providers._msgraph import patch_graph_host_os_header
from notify.providers.mail import ProviderEmail
from notify.providers.office365.credential import AuthFlow, MsalAsyncCredential, scopes_for
from notify.providers.office365.graph_mail import GraphMailSender, build_message, load_attachments, to_recipients
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

    async def _render_(
        self, to: list[Actor] = None, message: str = None, subject: str = None, **kwargs: Any
    ) -> str:
        """Render the HTML body once for every recipient.

        Args:
            to: The full recipient list (`ProviderEmail.batch_recipients=True`
                makes this the list, not one `Actor`).
            message: Plain-text/HTML body content, used as-is with no template.
            subject: The message subject (also passed into the template context).
            **kwargs: Extra template arguments; with a template, `recipient`
                and `username` are both bound to `to` (the list).

        Returns:
            str: The rendered HTML body.
        """
        if self._template:
            templateargs = {
                "recipient": to,
                "username": to,
                "message": message,
                "content": message,
                "subject": subject,
                **kwargs,
            }
            return await self._template.render_async(**templateargs)
        return kwargs.get("body") or message or ""

    async def _send_(
        self, to: list[Actor], message: str, subject: str = None, **kwargs: Any
    ) -> MailSendResult:
        """Build and send one Graph message to every recipient in `to`.

        Args:
            to: Every recipient for this `send()` call (batched — see
                `ProviderEmail.batch_recipients`).
            message: Plain-text/HTML body content (see `_render_`).
            subject: The message subject.
            **kwargs: `cc`, `bcc`, `reply_to`, `importance`, `attachments`,
                `inline_images`, `from_address`, `save_to_sent_items`, and
                `user_assertion` (On-Behalf-Of only) — popped from a copy so
                the caller's kwargs are never mutated. Anything else is
                forwarded to the template renderer.

        Returns:
            MailSendResult: The outcome of the one Graph send.

        Raises:
            NotifyAuthError: Missing mailbox for an app-only send, a missing
                On-Behalf-Of assertion, or an auth/permission Graph failure
                (via `GraphMailSender`/`map_odata_error`).
        """
        send_kwargs = dict(kwargs)
        user_assertion = send_kwargs.pop("user_assertion", None)
        cc = send_kwargs.pop("cc", None)
        bcc = send_kwargs.pop("bcc", None)
        reply_to = send_kwargs.pop("reply_to", None)
        importance = send_kwargs.pop("importance", None)
        attachments = send_kwargs.pop("attachments", None)
        inline_images = send_kwargs.pop("inline_images", None)
        from_address = send_kwargs.pop("from_address", None)
        save_to_sent_items = send_kwargs.pop("save_to_sent_items", self.save_to_sent_items)

        await self.connect()

        html = await self._render_(to, message, subject, **send_kwargs)
        loaded_attachments = await load_attachments(attachments=attachments, inline_images=inline_images)

        sender_address = from_address or self.sender
        graph_message = build_message(
            subject=subject,
            html=html,
            to=to_recipients(to),
            cc=to_recipients(cc),
            bcc=to_recipients(bcc),
            reply_to=to_recipients(reply_to),
            importance=importance,
            from_address=sender_address,
            attachments=loaded_attachments,
        )
        recipients = [r.email_address.address for r in (graph_message.to_recipients or [])]

        # App-only (client_credentials) always routes through /users/{mailbox};
        # every other flow is delegated to a specific user and routes through /me.
        if self._flow == AuthFlow.CLIENT_CREDENTIALS:
            mailbox = sender_address
            if not mailbox:
                raise NotifyAuthError(
                    "O365 app-only send requires a mailbox: pass from_address= "
                    "or configure sender=/O365_SENDER."
                )
        else:
            mailbox = None

        graph_sender = GraphMailSender(self._graph, provider=self.provider, logger=self.logger)

        if self._flow == AuthFlow.ON_BEHALF_OF:
            if not user_assertion:
                raise NotifyAuthError(
                    "O365 on_behalf_of send requires user_assertion= "
                    "(a per-send Graph-audience bearer token)."
                )
            with self._credential.use_assertion(user_assertion):
                return await graph_sender.send(
                    mailbox=mailbox,
                    message=graph_message,
                    attachments=loaded_attachments,
                    save_to_sent_items=save_to_sent_items,
                    recipients=recipients,
                )

        if user_assertion:
            self.logger.warning(
                "user_assertion was provided but auth_flow=%r (not on_behalf_of); ignoring it.",
                self._flow.value,
            )
        return await graph_sender.send(
            mailbox=mailbox,
            message=graph_message,
            attachments=loaded_attachments,
            save_to_sent_items=save_to_sent_items,
            recipients=recipients,
        )
