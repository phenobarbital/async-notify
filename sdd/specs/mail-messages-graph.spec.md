---
# SDD flow type and base branch (FEAT-145).
# - type: feature  (default)  → base_branch: dev (or any non-main branch)
# - type: hotfix              → base_branch MUST be: main
type: feature
base_branch: dev
---

# Feature Specification: Mail Messages via Microsoft Graph (send-as & On-Behalf-Of)

**Feature ID**: FEAT-004
**Date**: 2026-09-15
**Author**: Jesus Lara
**Status**: draft
**Target version**: 1.7.0
**Brainstorm**: `sdd/proposals/mail-messages-graph.brainstorm.md` (Recommended Option B)

---

## 1. Motivation & Business Requirements

> Can `office365` send email through **Microsoft Graph**, and can it send
> **"on behalf of"** another identity? Today: neither.

### Problem Statement

1. **`office365` does not use Graph.** `notify/providers/office365/office365.py` builds on the
   `O365` library with `MSOffice365Protocol` and the scope `https://outlook.office.com/.default`
   (office365.py:95), which is the legacy Outlook REST API. `o365` is pinned `<2.1` because 2.1
   removed `MSOffice365Protocol` (pyproject.toml:69), so the provider cannot be upgraded. On first
   run it calls `print()` + `input()` (office365.py:112-114), which breaks any server, worker or
   notify-server use. On failure it deletes `.o365_token.txt` and calls `connect()` again with no
   limit (office365.py:147-151). The `use_credentials=True` path uses basic auth
   (office365.py:175-179), which Exchange Online rejects. `docs/providers.rst` wrongly says it
   uses Graph.
2. **`outlook` depends on a broken package.** `notify/providers/outlook/outlook.py` uses
   `Office365-REST-Python-Client` (`office365.graph_client.GraphClient`, outlook.py:9), which the
   owner confirmed is broken and must be **removed completely**. It also sends with
   `client.me.send_mail(...)` (outlook.py:153), and `/me` fails with app-only tokens.
3. **No "on behalf of".** Neither provider can:
   - send **as another mailbox** (a shared mailbox, or another user) using Graph `from`/`sender`
     or `POST /users/{mailbox}/sendMail`, or
   - run the **OAuth2 On-Behalf-Of (OBO)** flow, where a middle-tier service exchanges a signed-in
     user's access token for a Graph token and sends mail as that user.

**Affected**: developers using `Notify("office365")` / `Notify("outlook")`, notify-server workers
(unattended, multi-user), and operators who bootstrap tokens by hand today.

### Goals

- G1. Rewrite `office365` on **Microsoft Graph** using **`msgraph-sdk`**, keeping the provider name.
- G2. Support **four auth flows** behind one MSAL-backed async credential:
  client credentials (app-only, **client secret or certificate**), **On-Behalf-Of** (user
  assertion), **delegated** (device-code bootstrap, then a silent cached refresh), and **ROPC**
  (legacy, `DeprecationWarning`).
- G3. Accept the OBO user token as a **per-send kwarg** (`user_assertion=`), so one provider
  instance serves many users, with MSAL caching exchanged tokens per assertion.
- G4. **Send-as**: an instance default `sender=` that each send can override with
  `from_address=`, for app-only and delegated/OBO flows.
- G5. **Pluggable token cache**: in-memory by default, plus file and **Redis** stores; persistent
  stores are **encrypted** (Fernet) unless `allow_unencrypted=True` is explicit.
- G6. Mail features: **one Graph message to all recipients** with To/CC/BCC/Reply-To/importance,
  a `save_to_sent_items` switch, attachments including **>3 MB through upload sessions**, and
  **inline CID images**.
- G7. **Auth/config errors are raised** (`NotifyAuthError`). Per-message delivery failures come
  back as a typed `MailSendResult`.
- G8. Move `outlook` onto the same Graph core. Remove `Office365-REST-Python-Client`, `o365` and
  `pyo365` from the `azure`/`all` extras.
- G9. The notify server **rejects queued jobs carrying `user_assertion`**, so user tokens never
  reach Redis.
- G10. A shared `notify/providers/_msgraph.py` (HostOs patch) used by `teams` and `office365`, plus
  a headless device-code CLI: `python -m notify.providers.office365.login`.
- G11. Keep the constructor backward compatible (`username`, `password`, `use_credentials`,
  `client_id`, `client_secret`, `tenant_id`) and add `auth_flow`. The interactive `input()` flow
  is removed.

### Non-Goals (explicitly out of scope)

- Reading mail, calendar, contacts or meeting scheduling (the docs claim these, but nothing
  implements them).
- Changing `teams` behaviour. Only its import of the HostOs patch moves.
- An interactive **authorization-code redirect** flow inside notify. Web apps hand notify a user
  assertion (OBO) instead.
- Encrypting OBO assertions so they can be queued. Queued OBO jobs are **rejected** (G9).
- Per-recipient personalised messages (one Graph message per `Actor`). `send()` builds **one
  message to all recipients**.
- Exchange tenant administration (Application Access Policy / RBAC for Applications). It is
  documented but not automated.
- Rejected in the brainstorm and not built here: native `azure-identity` credentials only
  (Option A, no Redis cache), a raw aiohttp Graph client (Option C, goes against the ms-graph
  direction), and SMTP XOAUTH2 (Option D, not Graph). See
  `sdd/proposals/mail-messages-graph.brainstorm.md`.

---

## 2. Architectural Design

### Overview

**Option B from the brainstorm**: `msgraph-sdk` handles all Graph HTTP (async, typed models,
`LargeFileUploadTask`). A single **MSAL-backed `AsyncTokenCredential`** fronts it. All four flows go
through MSAL (`ConfidentialClientApplication` / `PublicClientApplication`) and share one
`msal.SerializableTokenCache`, whose serialized state is kept in a **pluggable token store**
(memory | file | Redis, persistent stores Fernet-encrypted). MSAL calls are synchronous and run in
`loop.run_in_executor`. They are cache-first, so the network is hit only on a miss. Graph calls stay
fully async.

**User-facing behavior**

```python
# App-only daemon sending as a shared mailbox (one message to all recipients)
mail = Notify("office365", auth_flow="client_credentials", sender="noreply@contoso.com")
async with mail as m:
    [result] = await m.send(
        recipient=[alice, bob], subject="Report", template="report.html",
        cc=["ops@contoso.com"], attachments=["/tmp/report.pdf"],
        inline_images={"logo": "/srv/assets/logo.png"}, importance="high",
    )
    assert result.success

# OBO from a web handler: sends as the signed-in user; one long-lived instance for many users
mail = Notify("office365", auth_flow="on_behalf_of")
await mail.send(recipient=carol, subject="Approved", message=html,
                user_assertion=request_bearer_token)           # per send, never on the instance
# optional: from_address="team@contoso.com" (needs SendAs / SendOnBehalf on that mailbox)

# Delegated: one-time headless bootstrap, then silent sends
#   $ python -m notify.providers.office365.login --username me@contoso.com
mail = Notify("office365", auth_flow="delegated", username="me@contoso.com")

# Legacy — still works, logs DeprecationWarning (ROPC)
mail = Notify("office365", use_credentials=True)
# Alias — same Graph core
mail = Notify("outlook", client_id=..., client_secret=..., tenant_id=...)
```

**Resolved behaviour decisions** (from the brainstorm and the spec-time Q&A):

- Recipients: `send()` makes **one** Graph call per invocation, with every recipient in
  `toRecipients` plus `cc`/`bcc`/`reply_to`. The template renders **once**; `recipient` in the
  template context is the full recipient list.
- Errors: `NotifyAuthError` (invalid or expired assertion, missing consent, `ErrorSendAsDenied`,
  `ErrorAccessDenied`, 401/403, missing device-code bootstrap, an incomplete flow configuration) is
  **raised out of `send()`**. Any other Graph failure returns
  `MailSendResult(success=False, error=...)`.
- Mailbox routing: app-only always calls `/users/{mailbox}`, with mailbox = `from_address` or
  `sender` (**required**; raises `NotifyAuthError` if missing). Delegated/OBO call `/me` and set
  `Message.from_` when `from_address` or `sender` is given.
- `user_assertion` is **send-only**. Passing it to the constructor raises `ProviderError`. It is
  stripped from the kwargs forwarded to `sent` callbacks and never logged.

### Component Diagram

```
Notify("office365" | "outlook")                        notify/notify.py:31
        │
        ▼
Office365(ProviderEmail)  ── batch_recipients=True, raise_errors=(NotifyAuthError,),
        │                    redacted_send_kwargs={"user_assertion"}      (M5 hooks in mail.py)
        │ connect() [idempotent]
        ├──→ build_token_store(...) ──→ Memory | File | Redis TokenStore ──→ TokenCipher (Fernet)
        ├──→ MsalAsyncCredential(flow, …, token_store)                          (M3)
        │        ├─ CCA.acquire_token_for_client            (client_credentials, secret|cert)
        │        ├─ CCA.acquire_token_on_behalf_of          (on_behalf_of; assertion via ContextVar)
        │        ├─ PCA.acquire_token_silent                (delegated; seeded by login CLI)
        │        └─ CCA/PCA.acquire_token_by_username_password (password; DeprecationWarning)
        ├──→ GraphServiceClient(credentials=MsalAsyncCredential, scopes=flow scopes)
        │        (patch_graph_host_os_header() from notify/providers/_msgraph.py)       (M1)
        │
        │ _send_(to=list[Actor], …)
        ▼
graph_mail.load_attachments / build_message / GraphMailSender.send               (M4)
        ├─ small total  → POST /users/{m}|/me /sendMail  (save_to_sent_items)
        └─ large file(s)→ POST …/messages (draft) → createUploadSession + LargeFileUploadTask
                          → POST …/messages/{id}/send
        │
        ▼
MailSendResult  (notify/models.py)  |  NotifyAuthError raised

notify/server: NotifyClient.publish/stream/send + NotifyWrapper.__init__
        └─ reject_queued_secrets(message) → MessageError if "user_assertion" present      (M10)
```

### Integration Points

| Existing Component | Integration Type | Notes |
|---|---|---|
| `ProviderEmail` (`notify/providers/mail.py:15`) | extends + modifies | gains 3 opt-in class hooks (M5); defaults keep every other email provider unchanged |
| `ProviderBase` (`notify/providers/base.py:31`) | uses | `_prepare_` sets `self._template` (base.py:117-167); `__init__` copies unknown kwargs onto `self` (base.py:77-81), so Office365 must pop its kwargs first |
| `Notify` factory (`notify/notify.py:31`) | uses | unchanged; loads `notify.providers.office365` / `notify.providers.outlook` |
| `Office365` (`notify/providers/office365/office365.py:34`) | rewrite | Graph backend; the O365 import, `print`/`input`, recursive retry and file token backend are removed |
| `Outlook` (`notify/providers/outlook/outlook.py:22`) | rewrite → subclass of `Office365` | `office365.graph_client`/`msal` imports removed; `add_attachment(filename)` kept for compatibility |
| `teams` (`notify/providers/teams/teams.py:12,57`) | modifies (import only) | imports `patch_graph_host_os_header` from `notify.providers._msgraph`; `_msgraph_patch.py` becomes a re-export shim |
| `notify/conf.py:68-72` | modifies | new `O365_*` settings (auth flow, sender, certificate, token store, cipher key) |
| `notify/models.py` | extends | `MailSendResult`, `OutboundAttachment` (datamodel `BaseModel`) |
| `notify/exceptions.pyx:45` | uses | `NotifyAuthError(ProviderError)`; `MessageError` (exceptions.pyx:34) for queue rejection; **no `.pyx` change** |
| `notify/server/wrapper.py:40`, `client.py:99,108,130`, `server.py:504` | modifies | reject `user_assertion` before anything is written to Redis/TCP (client) and on wrapper construction (server) |
| `pyproject.toml:67-74, 81-99` | modifies | remove `pyo365`, `o365`, `Office365-REST-Python-Client`; add explicit `cryptography` to `azure` |
| `tests/test_outlook.py`, `tests/test_outlook1.py`, `notify/tests/base.py` | modifies | old tests patch `acquire_token` / `client`, which are removed |
| `docs/providers.rst` (~220 office365, ~467 outlook), `README.md`, `examples/test_o365.py`, `examples/test_outlook.py` | modifies | real feature list, flows, send-as, OBO, tenant setup |

### Data Models

```python
# notify/models.py  (extends; follows the file's datamodel pattern — from datamodel import BaseModel, Field, models.py:9)
class OutboundAttachment(BaseModel):
    """A file prepared for a Graph mail message (regular or inline CID)."""
    name: str = Field(required=True)
    content: bytes = Field(required=True, repr=False)
    content_type: str = Field(required=True, default="application/octet-stream")
    size: int = Field(required=True)
    content_id: Optional[str] = Field(required=False, default=None)   # set for inline CID images
    is_inline: bool = Field(required=False, default=False)


class MailSendResult(BaseModel):
    """Outcome of one Graph send() call (one message to all recipients)."""
    success: bool = Field(required=True)
    provider: str = Field(required=True)
    mailbox: Optional[str] = Field(required=False, default=None)      # None when sent via /me
    recipients: list[str] = Field(required=False, default_factory=list)
    strategy: Literal["send_mail", "draft_upload"] = Field(required=True, default="send_mail")
    message_id: Optional[str] = Field(required=False, default=None)   # draft id when strategy=draft_upload
    status_code: Optional[int] = Field(required=False, default=None)
    error_code: Optional[str] = Field(required=False, default=None)
    error: Optional[str] = Field(required=False, default=None)
```

### New Public Interfaces

```python
Notify("office365",
       auth_flow: Optional[Literal["client_credentials", "on_behalf_of", "delegated", "password"]] = None,
       client_id: str = None, client_secret: str = None, tenant_id: str = None,
       client_certificate_path: str = None, client_certificate_thumbprint: str = None,
       client_certificate_password: str = None,
       username: str = None, password: str = None, use_credentials: Optional[bool] = None,
       sender: str = None,
       token_store: Optional[Union[str, TokenStore]] = None,   # "memory" | "file" | "redis" | instance
       save_to_sent_items: bool = True)

await provider.send(recipient: Union[Actor, list[Actor]], message: str = None, subject: str = None,
                    template: str = None,
                    cc: list[str] = None, bcc: list[str] = None, reply_to: list[str] = None,
                    importance: Literal["low", "normal", "high"] = None,
                    attachments: list[Union[str, Path, OutboundAttachment]] = None,
                    inline_images: dict[str, Union[str, Path, bytes]] = None,
                    from_address: str = None, save_to_sent_items: bool = None,
                    user_assertion: str = None, **template_kwargs) -> list[MailSendResult]

$ python -m notify.providers.office365.login --username me@contoso.com [--tenant-id …] [--client-id …]
      [--token-store memory|file|redis]
```

---

## 3. Module Breakdown

#### Delegation-eligible modules

| Module | Eligible? | Decided patterns / exact contracts | Why not (if no) |
|---|---|---|---|
| M1: shared `_msgraph` module | yes | move the function verbatim; shim re-export; one import change in teams.py | — |
| M2: token stores + cipher | yes | ABC + 3 stores + Fernet cipher; key/opt-in rule fixed; Redis via `redis.asyncio` | — |
| M3: MSAL async credential | no | — | ContextVar assertion scoping, executor use and cache write-back need careful design review |
| M4: Graph mail builder/sender | yes | exact SDK builders, size thresholds, strategy switch and error mapping fixed below | — |
| M5: `ProviderEmail` opt-in hooks | yes | three class attributes and their exact semantics fixed; defaults are no-ops | — |
| M6: `Office365` provider rewrite | no | — | flow resolution precedence and legacy compatibility interact with M3/M5; needs the thinking model |
| M7: `Outlook` alias | yes | subclass + `add_attachment(filename)` compatibility shim | — |
| M8: device-code login CLI | yes | argparse entry point; stderr output; exit codes fixed | — |
| M9: config + dependencies | yes | exact setting names and pyproject edits listed | — |
| M10: notify-server OBO guard | yes | `reject_queued_secrets()` contract + four call sites fixed | — |
| M11: tests, docs, examples | no | — | integration test scenarios depend on tenant fixtures chosen during implementation |

### Module 1: Shared msgraph helper
- **Path**: `notify/providers/_msgraph.py` (new); `notify/providers/teams/_msgraph_patch.py` (shim); `notify/providers/teams/teams.py:12` (import)
- **Responsibility**: the one home of `patch_graph_host_os_header()` for every Graph-based provider.
- **Depends on**: `msgraph_core.middleware.telemetry.GraphTelemetryHandler` (verified: teams/_msgraph_patch.py:47)
- **Interface Skeleton**:
  ```python
  # notify/providers/_msgraph.py  (new — body moved verbatim from notify/providers/teams/_msgraph_patch.py:31-60)
  GRAPH_DEFAULT_SCOPE: str = "https://graph.microsoft.com/.default"

  def patch_graph_host_os_header() -> bool:
      """Sanitise msgraph-core's HostOs telemetry header (idempotent).

      Returns:
          True if the patch is in place, False if msgraph-core is absent or changed.
      """

  # notify/providers/teams/_msgraph_patch.py  (modifies — becomes a shim)
  from notify.providers._msgraph import patch_graph_host_os_header  # re-export, keeps old import path
  __all__ = ("patch_graph_host_os_header",)

  # notify/providers/teams/teams.py:12  (modifies)
  from notify.providers._msgraph import patch_graph_host_os_header  # was: from ._msgraph_patch import …
  ```

### Module 2: Token stores and cipher
- **Path**: `notify/providers/office365/token_store.py` (new)
- **Responsibility**: persist the serialized MSAL token cache behind an async interface. Encrypt it
  in persistent stores.
- **Depends on**: `cryptography.fernet.Fernet` (verified installed 46.0.7); `redis.asyncio`
  (verified: notify/server/client.py:6); `aiofiles` (verified: outlook.py:7); `notify.conf` (M9)
- **Rules**:
  - `MemoryTokenStore` needs no key.
  - `FileTokenStore` / `RedisTokenStore` raise `NotifyAuthError` at construction unless a cipher
    key is given or `allow_unencrypted=True`.
  - The file store writes with `0o600` permissions.
  - The Redis store uses key `f"{prefix}{key}"` (default prefix `"notify:o365:token:"`) and an
    optional TTL.
  - A value that fails to decrypt or parse is **deleted and treated as missing** (logged warning,
    no secret in the log).
  - When Redis fails, the store logs a warning and falls back to an in-memory copy for the rest of
    the process; it never blocks the send.
- **Interface Skeleton**:
  ```python
  # notify/providers/office365/token_store.py  (new)
  class TokenCipher:
      """Fernet encryption for serialized token caches."""
      def __init__(self, key: Union[str, bytes]) -> None:
          """Raises NotifyAuthError if the key is not a valid Fernet key."""
      def encrypt(self, plaintext: str) -> str: ...
      def decrypt(self, token: str) -> str:
          """Raises NotifyAuthError when the ciphertext is invalid or was made with another key."""

  class TokenStore(ABC):
      """Async persistence for one serialized MSAL token cache per key."""
      @abstractmethod
      async def load(self, key: str) -> Optional[str]:
          """Return the plaintext serialized cache, or None if absent or unreadable."""
      @abstractmethod
      async def save(self, key: str, value: str) -> None: ...
      @abstractmethod
      async def delete(self, key: str) -> None: ...
      async def close(self) -> None:
          """Release connections; default no-op."""

  class MemoryTokenStore(TokenStore):
      def __init__(self) -> None: ...

  class FileTokenStore(TokenStore):
      def __init__(self, directory: Union[str, Path], *, cipher_key: Optional[str] = None,
                   allow_unencrypted: bool = False) -> None: ...

  class RedisTokenStore(TokenStore):
      def __init__(self, url: str, *, cipher_key: Optional[str] = None, allow_unencrypted: bool = False,
                   prefix: str = "notify:o365:token:", ttl: Optional[int] = None) -> None: ...

  def build_token_store(kind: Optional[Union[str, TokenStore]] = None) -> TokenStore:
      """Resolve "memory" | "file" | "redis" | instance | None (→ O365_TOKEN_STORE, default "memory")
      using notify.conf settings. Raises NotifyAuthError for an unknown kind."""
  ```

### Module 3: MSAL-backed async credential
- **Path**: `notify/providers/office365/credential.py` (new)
- **Responsibility**: implement the `azure.core.credentials_async.AsyncTokenCredential` protocol
  for all four flows on one MSAL `SerializableTokenCache`, loaded from and saved to a `TokenStore`.
- **Depends on**: `msal` (verified 1.32.0: `ConfidentialClientApplication.acquire_token_on_behalf_of(user_assertion, scopes, claims_challenge=None, **kwargs)`, `PublicClientApplication.initiate_device_flow` / `acquire_token_by_device_flow`, `ClientApplication.__init__(token_cache=)`, `SerializableTokenCache.has_state_changed`); `azure.core.credentials.AccessToken` (fields `token`, `expires_on`); M2.
- **Rules**:
  - Cache key: `f"{tenant_id}:{client_id}:{flow.value}"`.
  - The cache is loaded lazily on the first `get_token`. It is saved only when
    `has_state_changed`, under an `asyncio.Lock`.
  - Every MSAL call runs through `loop.run_in_executor(None, …)`.
  - OBO assertions are scoped with a module-level
    `ContextVar[Optional[str]]` set by `use_assertion()`; `get_token` for the `on_behalf_of` flow
    raises `NotifyAuthError` when none is set.
  - MSAL error dicts (`error`, `error_description`, `correlation_id`) become `NotifyAuthError`
    messages. The assertion, secrets and tokens are never included.
  - `claims` from Kiota go to MSAL as `claims_challenge`. `enable_cae` is accepted and ignored.
  - `password` flow: `warnings.warn(..., DeprecationWarning)` once per instance. It uses a
    `ConfidentialClientApplication` when a secret or certificate exists, otherwise a
    `PublicClientApplication`.
  - `delegated` flow: `acquire_token_silent(scopes, account)` for the account whose `username`
    matches (case-insensitive). With no cached account it raises
    `NotifyAuthError("… run: python -m notify.providers.office365.login --username …")`.
- **Interface Skeleton**:
  ```python
  # notify/providers/office365/credential.py  (new)
  class AuthFlow(str, Enum):
      CLIENT_CREDENTIALS = "client_credentials"
      ON_BEHALF_OF = "on_behalf_of"
      DELEGATED = "delegated"
      PASSWORD = "password"

  DELEGATED_SCOPES: tuple[str, ...] = ("https://graph.microsoft.com/Mail.Send",
                                       "https://graph.microsoft.com/Mail.Send.Shared")

  def scopes_for(flow: AuthFlow) -> list[str]:
      """[GRAPH_DEFAULT_SCOPE] for client_credentials/on_behalf_of/password; DELEGATED_SCOPES for delegated."""

  class MsalAsyncCredential:
      """AsyncTokenCredential backed by MSAL with a pluggable token cache."""
      def __init__(self, *, flow: AuthFlow, tenant_id: str, client_id: str,
                   client_secret: Optional[str] = None,
                   client_certificate_path: Optional[str] = None,
                   client_certificate_thumbprint: Optional[str] = None,
                   client_certificate_password: Optional[str] = None,
                   username: Optional[str] = None, password: Optional[str] = None,
                   token_store: TokenStore,
                   authority_host: str = "https://login.microsoftonline.com") -> None:
          """Raises NotifyAuthError when required inputs for `flow` are missing."""

      async def get_token(self, *scopes: str, claims: Optional[str] = None,
                          tenant_id: Optional[str] = None, enable_cae: bool = False,
                          **kwargs: Any) -> AccessToken:
          """Cache-first token for the configured flow. Raises NotifyAuthError on any MSAL failure."""
          # signature verified: azure.core.credentials_async.AsyncTokenCredential.get_token

      @contextmanager
      def use_assertion(self, user_assertion: str) -> Iterator[None]:
          """Bind a user assertion to the current asyncio context for OBO get_token calls."""

      async def initiate_device_flow(self, scopes: Optional[list[str]] = None) -> dict:
          """Start a device-code flow (delegated only); returns MSAL's flow dict (user_code, message…)."""

      async def complete_device_flow(self, flow: dict) -> None:
          """Block (in executor) until the user signs in; persists the cache. Raises NotifyAuthError."""

      async def close(self) -> None:
          """Persist a changed cache and close the token store."""

      async def __aenter__(self) -> "MsalAsyncCredential": ...
      async def __aexit__(self, *exc: Any) -> None: ...
  ```

### Module 4: Graph mail builder and sender
- **Path**: `notify/providers/office365/graph_mail.py` (new)
- **Responsibility**: turn render output and send kwargs into `msgraph` models, choose a send
  strategy, run it, and map Graph errors.
- **Depends on**: verified SDK symbols in §6; `OutboundAttachment`, `MailSendResult` (notify/models.py, new); `aiofiles`
- **Rules**:
  - `INLINE_REQUEST_LIMIT = 3 * 1024 * 1024` applies to the summed raw size of all attachments,
    inline images included.
  - `MAX_ATTACHMENT_SIZE = 150 * 1024 * 1024` per file. Larger files raise `ProviderError` before
    any Graph call.
  - Strategy `send_mail`: total ≤ limit, so everything goes in `Message.attachments` as
    `FileAttachment` (odata type `#microsoft.graph.fileAttachment`) and one
    `send_mail.post(SendMailPostRequestBody(message=…, save_to_sent_items=…))` call is made.
  - Strategy `draft_upload`: total > limit. Create a draft through `messages.post(message)` with
    the small attachments and inline images (≤ limit, inline images first). Upload each remaining
    file with `attachments.create_upload_session.post(CreateUploadSessionPostRequestBody(attachment_item=AttachmentItem(attachment_type=AttachmentType.File, name, size, content_type)))`
    plus `LargeFileUploadTask(session, graph.request_adapter, BytesIO(content)).upload()`, then call
    `messages.by_message_id(id).send.post()`. A draft always lands in Sent Items, so when
    `save_to_sent_items=False` a warning is logged. If upload or send fails, the draft is deleted
    (best effort).
  - The route builder is `graph.me` when `mailbox is None`, else `graph.users.by_user_id(mailbox)`.
    Both return `UserItemRequestBuilder` (verified).
  - `map_odata_error`: `response_status_code in (401, 403)` or `error.code in AUTH_ERROR_CODES`
    → `NotifyAuthError`. Anything else → `MailSendResult(success=False, status_code, error_code, error)`.
    `ErrorInvalidRecipients` / 400 → a result, not raised. `ErrorInvalidUser` (unknown mailbox)
    is deliberately **not** an auth code; it is a delivery failure.
  - CID: every `inline_images` key becomes `content_id` with `is_inline=True`. A `cid:<key>` in the
    HTML with no matching image logs a warning. An image that the HTML never references is still
    attached, with a debug log.
  - Content type: `mimetypes.guess_type(name)[0] or "application/octet-stream"`.
- **Interface Skeleton**:
  ```python
  # notify/providers/office365/graph_mail.py  (new)
  INLINE_REQUEST_LIMIT: int = 3 * 1024 * 1024
  MAX_ATTACHMENT_SIZE: int = 150 * 1024 * 1024
  AUTH_ERROR_CODES: frozenset[str] = frozenset({
      "ErrorSendAsDenied", "ErrorAccessDenied", "AccessDenied", "InvalidAuthenticationToken",
      "Authorization_RequestDenied", "MailboxNotEnabledForRESTAPI",
  })

  async def load_attachments(attachments: Optional[list[Union[str, Path, OutboundAttachment]]] = None,
                             inline_images: Optional[dict[str, Union[str, Path, bytes]]] = None
                             ) -> list[OutboundAttachment]:
      """Read files asynchronously. Raises FileNotFoundError for missing paths, ProviderError above MAX_ATTACHMENT_SIZE."""

  def to_recipients(addresses: Optional[Iterable[Union[str, Actor]]]) -> list[Recipient]:
      """Actor → Recipient(EmailAddress(address=actor.account.address, name=actor.name)); str → address only.
      Actors whose account.address is a list contribute every address."""

  def build_message(*, subject: Optional[str], html: str, to: list[Recipient],
                    cc: Optional[list[Recipient]] = None, bcc: Optional[list[Recipient]] = None,
                    reply_to: Optional[list[Recipient]] = None, importance: Optional[str] = None,
                    from_address: Optional[str] = None,
                    attachments: Optional[list[OutboundAttachment]] = None) -> Message:
          """Body is BodyType.Html. Importance maps to msgraph Importance(Low|Normal|High); anything else raises ValueError."""

  def map_odata_error(exc: ODataError, *, provider: str, mailbox: Optional[str],
                      recipients: list[str]) -> MailSendResult:
      """Raises NotifyAuthError for auth/permission failures; otherwise returns a failed MailSendResult."""

  class GraphMailSender:
      """Execute a Graph mail send using the send_mail or draft_upload strategy."""
      def __init__(self, graph: GraphServiceClient, *, provider: str, logger: logging.Logger) -> None: ...

      async def send(self, *, mailbox: Optional[str], message: Message,
                     attachments: list[OutboundAttachment], save_to_sent_items: bool,
                     recipients: list[str]) -> MailSendResult:
          """Choose the strategy by total attachment size, send, and return MailSendResult.
          Raises NotifyAuthError (via map_odata_error) for auth/permission failures."""
  ```

### Module 5: `ProviderEmail` opt-in hooks
- **Path**: `notify/providers/mail.py` (modifies `ProviderEmail` class attrs at :22-24 and `send()` at :209-257)
- **Responsibility**: let a provider (a) receive every recipient in one `_send_` call, (b) re-raise
  chosen exception types instead of hiding them, and (c) keep secrets out of `sent` callbacks, all
  **without overriding `send()`** (codebase convention).
- **Rules**:
  - Defaults are `batch_recipients = False`, `raise_errors = ()` and
    `redacted_send_kwargs = frozenset()`, which reproduce today's behaviour exactly for
    `email`, `gmail`, `smtp`, `sendgrid`, and `ses` (ses overrides `send()` at ses.py:158 and is
    unaffected).
  - When `batch_recipients` is True, `send()` calls `_send_(recipients, message, subject=subject, **kwargs)`
    **once** with the list, appends its result, and calls `__sent__(recipients, message, result, …)`
    once.
  - `connect()` errors whose type is in `raise_errors` are re-raised unchanged instead of being
    wrapped in `ProviderError` (mail.py:225-228). Per-recipient/batch exceptions of those types are
    re-raised after `self.logger.warning`.
  - Keys in `redacted_send_kwargs` are removed from the kwargs passed to `__sent__` (base.py:226)
    and so to the user `sent` callback.
- **Interface Skeleton**:
  ```python
  # notify/providers/mail.py  (modifies notify/providers/mail.py:15-24, :209)
  class ProviderEmail(ProviderBase, ABC):  # verified: mail.py:15
      provider_type = ProviderType.EMAIL    # verified: mail.py:22
      blocking: str = 'asyncio'             # verified: mail.py:23
      timeout: int = 60                     # verified: mail.py:24
      batch_recipients: bool = False
      """When True, send() calls _send_ once with the full recipient list."""
      raise_errors: tuple[type[BaseException], ...] = ()
      """Exception types re-raised by send() instead of being logged and swallowed."""
      redacted_send_kwargs: frozenset[str] = frozenset()
      """Send kwargs never forwarded to __sent__ / the `sent` callback."""

      async def send(self, recipient: list[Actor] = None, message: Union[str, Any] = None,
                     subject: str = None, **kwargs):  # verified: mail.py:209
          """Unchanged contract; honours the three hooks above."""
  ```

### Module 6: `Office365` provider rewrite
- **Path**: `notify/providers/office365/office365.py` (rewrite), `notify/providers/office365/__init__.py` (docstring + exports)
- **Responsibility**: the Graph-based email provider. It resolves the flow, wires M2/M3/M4, and
  implements `connect` / `close` / `_render_` / `_send_`.
- **Depends on**: M1, M2, M3, M4, M5, M9
- **Rules — flow resolution precedence** (first match wins):
  1. the `auth_flow` kwarg, then
  2. the `O365_AUTH_FLOW` setting, then
  3. `use_credentials is True` (explicitly passed) → `password` (`DeprecationWarning`), then
  4. `client_secret` or `client_certificate_path` available → `client_credentials`, then
  5. `username` and `password` available → `password` (`DeprecationWarning`), then
  6. otherwise raise `NotifyAuthError` listing the missing settings.

  `use_credentials` now defaults to `None` (it was `True`, office365.py:49). Any kwarg the
  provider consumes is **popped before `super().__init__`** (base.py:77-81 would otherwise set it
  on `self`). `user_assertion` in the constructor → `ProviderError`.
- **Rules — lifecycle**:
  - `connect()` is **idempotent**: when `self._graph` is set it returns at once. This matters
    because `ProviderEmail.send()` calls `connect()` on every send (mail.py:224) and `__aenter__`
    calls it too (base.py:84).
  - `connect()` makes **no network call**; tokens are acquired lazily on the first Graph request.
  - `close()` closes the credential (which persists the cache and closes the store) and clears
    `_graph`.
- **Rules — send**:
  - `_render_(to=list[Actor], message, subject, **kwargs) -> str` renders the template once with
    `recipient=to` (the list), `username=to`, `message`, `content`, `subject`, `**kwargs`. With no
    template it uses `kwargs["body"]` or `message`.
  - `_send_(to: list[Actor], message, subject, **kwargs) -> MailSendResult`:
    - pops `user_assertion`, `cc`, `bcc`, `reply_to`, `importance`, `attachments`,
      `inline_images`, `from_address` and `save_to_sent_items` from a **copy** of kwargs;
    - renders, loads attachments, builds the message, and resolves the mailbox;
    - when `flow is ON_BEHALF_OF`, wraps the `GraphMailSender.send` call in
      `self._credential.use_assertion(user_assertion)`. A missing assertion raises
      `NotifyAuthError`. An assertion passed to any other flow is ignored with a warning.
- **Interface Skeleton**:
  ```python
  # notify/providers/office365/office365.py  (rewrite of notify/providers/office365/office365.py:34)
  class Office365(ProviderEmail):  # ProviderEmail verified: notify/providers/mail.py:15
      """Microsoft Graph email provider (app-only, On-Behalf-Of, delegated, legacy ROPC).

      Sends one message to all recipients through msgraph-sdk, with send-as routing,
      CC/BCC/Reply-To, inline CID images and upload-session attachments.
      """
      provider = "office365"                           # verified: office365.py:41
      blocking: str = 'asyncio'                        # verified: office365.py:42
      batch_recipients = True
      raise_errors = (NotifyAuthError,)
      redacted_send_kwargs = frozenset({"user_assertion"})

      def __init__(self, *args, auth_flow: Optional[Union[str, AuthFlow]] = None,
                   username: str = None, password: str = None, use_credentials: Optional[bool] = None,
                   client_id: str = None, client_secret: str = None, tenant_id: str = None,
                   client_certificate_path: str = None, client_certificate_thumbprint: str = None,
                   client_certificate_password: str = None,
                   sender: str = None, token_store: Optional[Union[str, TokenStore]] = None,
                   save_to_sent_items: bool = True, **kwargs) -> None:
          """Resolve the auth flow and validate settings. Raises NotifyAuthError / ProviderError."""

      @property
      def auth_flow(self) -> AuthFlow: ...

      async def connect(self, *args, **kwargs) -> None:
          """Idempotently build token store, MsalAsyncCredential and GraphServiceClient (no network)."""

      async def close(self) -> None:
          """Persist the token cache and release the Graph client and store."""

      async def _render_(self, to: list[Actor] = None, message: str = None, subject: str = None,
                         **kwargs) -> str:
          """Render the HTML body once for all recipients."""

      async def _send_(self, to: list[Actor], message: str, subject: str = None,
                       **kwargs) -> MailSendResult:
          """Build and send one Graph message. Raises NotifyAuthError; returns MailSendResult otherwise."""
  ```

### Module 7: `Outlook` alias
- **Path**: `notify/providers/outlook/outlook.py` (rewrite), `notify/providers/outlook/__init__.py`
- **Responsibility**: keep `Notify("outlook", …)` working on the Graph core; no REST-client imports.
- **Depends on**: M6
- **Rules**:
  - `provider = "outlook"`.
  - `add_attachment(filename)` keeps its async signature (outlook.py:103). It queues the path in
    `self._pending_attachments`, which `_send_` merges into `attachments` and clears after each
    send. A missing file raises `FileNotFoundError` immediately, as it does today.
  - `acquire_token` / `acquire_token_by_username` are **removed** (breaking for direct callers;
    noted in §7).
- **Interface Skeleton**:
  ```python
  # notify/providers/outlook/outlook.py  (rewrite of notify/providers/outlook/outlook.py:22)
  from notify.providers.office365.office365 import Office365

  class Outlook(Office365):
      """Alias of the Graph-based Office365 provider kept for backward compatibility."""
      provider = "outlook"                               # verified: outlook.py:29

      async def add_attachment(self, filename: Union[str, Path]) -> None:  # verified: outlook.py:103
          """Queue a file to attach to the next send(). Raises FileNotFoundError."""

      async def _send_(self, to: list[Actor], message: str, subject: str = None,
                       **kwargs) -> MailSendResult:
          """Merge queued attachments into kwargs['attachments'], delegate to Office365._send_, clear queue."""
  ```

### Module 8: Device-code login CLI
- **Path**: `notify/providers/office365/login.py` (new)
- **Responsibility**: headless one-time delegated sign-in that seeds the configured token store.
- **Depends on**: M2, M3, M9
- **Rules**:
  - Messages go to `sys.stderr.write` (CLI output; no `print`).
  - Exit codes: `0` on success, `1` for `NotifyAuthError` (including a device-code timeout),
    `2` for invalid arguments.
  - Refuses to run with `--token-store memory` (exit 2, "memory store would lose the token").
- **Interface Skeleton**:
  ```python
  # notify/providers/office365/login.py  (new)
  async def device_code_login(*, username: str, tenant_id: str, client_id: str,
                              token_store: TokenStore) -> None:
      """Run MsalAsyncCredential(flow=DELEGATED) initiate/complete device flow and persist the cache."""

  def main(argv: Optional[list[str]] = None) -> int:
      """argparse: --username (required), --tenant-id, --client-id, --token-store {file,redis}."""

  if __name__ == "__main__":
      raise SystemExit(main())
  ```

### Module 9: Configuration and dependencies
- **Path**: `notify/conf.py` (modifies :68-72 block), `pyproject.toml` (modifies :67-74, :81-99)
- **Responsibility**: new navconfig settings, and removal of the dead Microsoft libraries.
- **Interface Skeleton**:
  ```python
  # notify/conf.py  (extends the "# Office 365" block, verified: conf.py:67-72)
  O365_AUTH_FLOW = config.get("O365_AUTH_FLOW")                       # None → resolution rules (M6)
  O365_SENDER = config.get("O365_SENDER")
  O365_CLIENT_CERTIFICATE_PATH = config.get("O365_CLIENT_CERTIFICATE_PATH")
  O365_CLIENT_CERTIFICATE_THUMBPRINT = config.get("O365_CLIENT_CERTIFICATE_THUMBPRINT")
  O365_CLIENT_CERTIFICATE_PASSWORD = config.get("O365_CLIENT_CERTIFICATE_PASSWORD")
  O365_TOKEN_STORE = config.get("O365_TOKEN_STORE", fallback="memory")  # memory | file | redis
  O365_TOKEN_STORE_DIR = config.get("O365_TOKEN_STORE_DIR", fallback=str(BASE_DIR.joinpath(".o365")))
  O365_TOKEN_STORE_REDIS = config.get("O365_TOKEN_STORE_REDIS", fallback=NOTIFY_REDIS)  # NOTIFY_REDIS verified: conf.py:17
  O365_TOKEN_STORE_TTL = config.getint("O365_TOKEN_STORE_TTL", fallback=0)  # 0 → no TTL
  O365_TOKEN_CIPHER_KEY = config.get("O365_TOKEN_CIPHER_KEY")          # Fernet key (urlsafe base64, 32 bytes)
  O365_TOKEN_ALLOW_UNENCRYPTED = config.getboolean("O365_TOKEN_ALLOW_UNENCRYPTED", fallback=False)
  ```
  ```toml
  # pyproject.toml — azure extra (verified lines 67-74) becomes:
  azure = [
    "msal>=1.32.0",
    "msgraph-core>=1.3.2",
    "azure-identity>=1.23.0",
    "msgraph-sdk>=1.22.0",
    "cryptography>=42.0",
  ]
  # all extra (verified lines 81-99): drop "o365>=2.0.37,<2.1" (:86) and "Office365-REST-Python-Client>=2.5.13" (:87); add "cryptography>=42.0".
  ```
  > `BASE_DIR` and `config` are already imported (`from navconfig import BASE_DIR, config`, conf.py:3).

### Module 10: Notify-server OBO guard
- **Path**: `notify/server/wrapper.py` (new function + call in `NotifyWrapper.__init__` :40), `notify/server/client.py` (calls in `publish` :99, `stream` :108, `send` :130)
- **Responsibility**: make sure a user assertion never gets serialized into Redis or TCP payloads.
- **Rules**:
  - The check covers the top-level `message` dict keys and its `kwargs` dict when one is present.
  - The error message names the key but never its value.
  - The client checks **before** `json.dumps` / `cloudpickle.dumps`.
- **Interface Skeleton**:
  ```python
  # notify/server/wrapper.py  (modifies; NotifyWrapper verified: wrapper.py:18, __init__ :40)
  QUEUE_FORBIDDEN_KWARGS: frozenset[str] = frozenset({"user_assertion"})

  def reject_queued_secrets(message: dict) -> None:
      """Raise MessageError if a queued notification carries a forbidden secret kwarg.

      Raises:
          MessageError: e.g. "user_assertion cannot be queued; send On-Behalf-Of mail directly".
      """

  # notify/server/client.py  (modifies publish :99, stream :108, send :130)
  #   first statement of each: reject_queued_secrets(message)
  # notify/server/wrapper.py NotifyWrapper.__init__ (:40)
  #   first statement: reject_queued_secrets({**kwargs})
  ```

### Module 11: Tests, docs, examples
- **Path**: `tests/test_office365_graph.py` (new), `tests/test_office365_token_store.py` (new), `tests/test_office365_credential.py` (new), `tests/test_mail_hooks.py` (new), `tests/test_notify_server_guard.py` (new), `tests/test_outlook.py` + `tests/test_outlook1.py` (rewrite), `tests/integration/test_office365_live.py` (new, `@pytest.mark.integration`), `docs/providers.rst`, `README.md`, `examples/test_o365.py`, `examples/test_outlook.py`
- **Responsibility**: offline coverage with a mocked Graph client and MSAL; live tests against the
  existing tenant, gated on navconfig credentials (skipped when absent); accurate docs.
- **Depends on**: M1–M10

---

## 4. Test Specification

### Unit Tests
| Test | Module | Description |
|---|---|---|
| `test_msgraph_shim_reexports_patch` | M1 | `teams._msgraph_patch.patch_graph_host_os_header is notify.providers._msgraph.patch_graph_host_os_header` |
| `test_memory_store_roundtrip` | M2 | save/load/delete |
| `test_file_store_requires_key_or_opt_in` | M2 | no key and `allow_unencrypted=False` → `NotifyAuthError` |
| `test_file_store_encrypted_on_disk_and_0600` | M2 | the file bytes do not contain the plaintext; mode is `0o600` |
| `test_store_corrupt_value_is_discarded` | M2 | a wrong key/garbage value → `load` returns None and the entry is deleted |
| `test_redis_store_fallback_on_connection_error` | M2 | a mocked Redis failure → warning + in-memory behaviour |
| `test_credential_client_credentials_secret` | M3 | mocked CCA `acquire_token_for_client` → `AccessToken` |
| `test_credential_client_credentials_certificate` | M3 | the certificate dict is passed as `client_credential` |
| `test_credential_obo_requires_assertion` | M3 | `get_token` with no `use_assertion` → `NotifyAuthError` |
| `test_credential_obo_contexts_isolated` | M3 | two concurrent tasks with different assertions each get their own token |
| `test_credential_delegated_without_account_hints_login` | M3 | error message contains `notify.providers.office365.login` |
| `test_credential_password_warns` | M3 | `DeprecationWarning` emitted |
| `test_credential_persists_only_on_change` | M3 | `store.save` is called only when `has_state_changed` |
| `test_credential_error_never_leaks_secrets` | M3 | the exception text contains neither the assertion nor the secret |
| `test_build_message_recipients_cc_bcc_reply_importance` | M4 | model fields populated; bad importance → `ValueError` |
| `test_send_mail_strategy_small` | M4 | `users.by_user_id(m).send_mail.post` called once with `save_to_sent_items` |
| `test_draft_upload_strategy_large` | M4 | draft → upload session → `send.post`; small files stay inline |
| `test_draft_deleted_on_upload_failure` | M4 | best-effort delete called |
| `test_attachment_over_150mb_rejected` | M4 | `ProviderError` before any Graph call |
| `test_inline_cid_attachment` | M4 | `is_inline=True`, `content_id` = key; missing reference → warning |
| `test_map_odata_error_auth_raises` | M4 | 403 / `ErrorSendAsDenied` → `NotifyAuthError` |
| `test_map_odata_error_other_returns_result` | M4 | 400 `ErrorInvalidRecipients` → `MailSendResult(success=False)` |
| `test_email_hooks_default_unchanged` | M5 | a dummy `ProviderEmail` subclass keeps per-recipient calls and swallowed errors |
| `test_email_hooks_batch` | M5 | `_send_` called once with the list; `__sent__` once |
| `test_email_hooks_raise_errors` | M5 | the listed exception propagates from `connect()` and `_send_` |
| `test_email_hooks_redacted_kwargs` | M5 | the `sent` callback never receives `user_assertion` |
| `test_flow_resolution_precedence` | M6 | the 6 precedence rules, including `use_credentials=True` → password + warning |
| `test_constructor_rejects_user_assertion` | M6 | `ProviderError` |
| `test_consumed_kwargs_not_set_on_self` | M6 | e.g. no `self.client_certificate_password` leak through `ProviderBase.__init__` |
| `test_connect_idempotent_no_network` | M6 | two `connect()` calls → one Graph client; MSAL not called |
| `test_app_only_requires_mailbox` | M6 | no `sender` / `from_address` → `NotifyAuthError` |
| `test_obo_send_uses_me_and_assertion` | M6 | `graph.me` route; credential saw the assertion |
| `test_send_as_from_address_overrides_sender` | M6 | app-only route uses `from_address`; delegated sets `Message.from_` |
| `test_send_returns_single_result_for_many_recipients` | M6 | `send([a, b])` → `[MailSendResult]` with both addresses |
| `test_outlook_is_office365_subclass` | M7 | `Notify("outlook")` loads `Outlook`, no `office365.graph_client` import |
| `test_outlook_add_attachment_queue` | M7 | the queued file is attached once, then cleared; missing file → `FileNotFoundError` |
| `test_login_cli_refuses_memory_store` | M8 | exit code 2 |
| `test_login_cli_success_persists_cache` | M8 | mocked device flow → `store.save` called; exit 0 |
| `test_reject_queued_secrets` | M10 | top-level and nested `kwargs` → `MessageError`; the value is not in the message |
| `test_client_stream_rejects_before_redis` | M10 | `redis.xadd` not called |
| `test_no_removed_libraries_imported` | M6/M7/M9 | importing both providers never imports `O365`, `office365`, `pyo365` |

### Integration Tests
| Test | Description |
|---|---|
| `test_live_app_only_send_as_shared_mailbox` | client credentials → send to a test mailbox from the shared mailbox (`O365_SENDER`) |
| `test_live_app_only_large_attachment` | a 5 MB attachment uses `draft_upload` and arrives |
| `test_live_cc_bcc_inline_image` | recipients plus a CID image rendered |
| `test_live_obo_send` | obtain a user token for the API scope (test helper), send with `user_assertion` |
| `test_live_delegated_silent_after_seed` | a pre-seeded file/redis store sends without interaction |
| `test_live_send_as_denied_raises` | `from_address` set to a mailbox without rights → `NotifyAuthError` |

Integration tests carry `@pytest.mark.integration` (pytest.ini marker) and skip when
`O365_CLIENT_ID` / `O365_TENANT_ID` / test mailbox settings are missing.

### Test Data / Fixtures
```python
@pytest.fixture
def graph_client_mock():
    """MagicMock GraphServiceClient whose users.by_user_id(...) / me builders expose AsyncMock
    send_mail.post, messages.post, messages.by_message_id(...).send.post and
    .attachments.create_upload_session.post; request_adapter is a MagicMock."""

@pytest.fixture
def msal_cca_mock(monkeypatch):
    """Patch msal.ConfidentialClientApplication with acquire_token_for_client /
    acquire_token_on_behalf_of returning {"access_token": "t", "expires_in": 3600}."""

@pytest.fixture
def fernet_key() -> str:
    return Fernet.generate_key().decode()

@pytest.fixture
def actors() -> list[Actor]:
    return [Actor(name="Alice", account={"address": "alice@contoso.com"}),
            Actor(name="Bob", account={"address": "bob@contoso.com"})]
```

---

## 5. Acceptance Criteria

> This feature is complete when ALL of the following are true:

- [ ] AC1 — `Notify("office365", …)` sends through **Microsoft Graph** (`msgraph-sdk`); no code
  path imports `O365`, `office365` (the REST client) or `pyo365`.
- [ ] AC2 — All four flows work: `client_credentials` (secret **and** certificate),
  `on_behalf_of`, `delegated` (after the device-code CLI), `password` (with `DeprecationWarning`).
- [ ] AC3 — OBO takes the token only as the per-send `user_assertion`. One provider instance sends
  for two different users concurrently without mixing tokens (unit test
  `test_credential_obo_contexts_isolated`). A constructor-level `user_assertion` raises
  `ProviderError`.
- [ ] AC4 — Send-as: the instance `sender` is used by default and `from_address` overrides it per
  send. App-only uses `/users/{mailbox}` and never `/me`. Delegated/OBO set `Message.from_`.
- [ ] AC5 — The token store is pluggable (`memory` default, `file`, `redis`). Persistent stores
  refuse to start without `O365_TOKEN_CIPHER_KEY` unless `allow_unencrypted=True`. Encrypted data
  at rest never contains a plaintext token.
- [ ] AC6 — One `send()` call issues **one** Graph message to all recipients, with working
  CC/BCC/Reply-To/importance and a single `MailSendResult` in the returned list.
- [ ] AC7 — Attachments ≤ 3 MB total go inline. Larger files go through upload sessions (≤ 150 MB
  each; larger is rejected before any Graph call). Inline CID images render.
- [ ] AC8 — `save_to_sent_items` is honoured for the `send_mail` strategy (instance default,
  per-send override). The `draft_upload` strategy logs a warning when it is False.
- [ ] AC9 — Auth/permission failures raise `NotifyAuthError` out of `send()`. Other Graph failures
  return `MailSendResult(success=False, …)`. Neither leaks assertions, secrets or tokens into
  logs, exceptions or `sent` callback kwargs.
- [ ] AC10 — No `print()` / `input()` in either provider. `connect()` is idempotent and makes no
  network call.
- [ ] AC11 — Legacy constructor kwargs (`username`, `password`, `use_credentials`, `client_id`,
  `client_secret`, `tenant_id`) are still accepted, and flow resolution follows §3 M6 precedence.
- [ ] AC12 — `Notify("outlook", …)` works as a subclass of `Office365`. `Outlook.add_attachment(filename)`
  still works.
- [ ] AC13 — `ProviderEmail` hook defaults leave `email`, `gmail`, `smtp`, `sendgrid` and `ses`
  behaviour unchanged (existing `tests/test_email_utf8.py`, `tests/test_ses.py` pass unmodified).
- [ ] AC14 — The notify server/client rejects any message carrying `user_assertion` with
  `MessageError` before writing to Redis/TCP.
- [ ] AC15 — `notify/providers/_msgraph.py` holds the HostOs patch. `teams` imports it from there,
  and the old `teams._msgraph_patch` import path still works.
- [ ] AC16 — `python -m notify.providers.office365.login --username …` seeds a file/redis store
  with no browser redirect.
- [ ] AC17 — `pyproject.toml`: `pyo365`, `o365`, `Office365-REST-Python-Client` removed from
  `azure` and `all`, and `cryptography` added. New settings live in `notify/conf.py` (no
  `os.environ` in providers).
- [ ] AC18 — Every unit test in §4 passes: `pytest tests/test_office365_graph.py tests/test_office365_token_store.py tests/test_office365_credential.py tests/test_mail_hooks.py tests/test_notify_server_guard.py tests/test_outlook.py tests/test_outlook1.py -v`.
- [ ] AC19 — Integration tests pass against the existing tenant: `pytest -m integration tests/integration/test_office365_live.py -v`.
- [ ] AC20 — `docs/providers.rst` (office365 + outlook sections), `README.md` and both examples
  describe the real flows, send-as, OBO, token stores and the required tenant setup (app
  permissions, exposed API scope for OBO, SendAs/SendOnBehalf, Application Access Policy).
- [ ] AC21 — Google-style docstrings and strict type hints on every new or changed public
  function and class; `flake8` clean at 120 columns.

---

## 6. Codebase Contract

> **CRITICAL — Anti-Hallucination Anchor**
> Re-verified on `dev` @ `d7f6840` (2026-09-15). `notify/` is unchanged since the brainstorm
> commit `7adbc70`; only `Makefile`/`pyproject.toml` pins moved, and the extras lines below were
> re-read.

### Verified Imports
```python
# project
from notify.providers.mail import ProviderEmail            # verified: notify/providers/mail.py:15
from notify.providers.base import ProviderBase, ProviderType  # verified: notify/providers/base.py:23,31
from notify.exceptions import NotifyAuthError, ProviderError, MessageError, NotifyException
    # verified: notify/exceptions.pyx:45 (NotifyAuthError(ProviderError)), :30, :34, :5
    # NOTE: NotifyAuthError is declared in exceptions.pyx only (not in exceptions.pxd) — Python import works
from notify.models import Actor, Account                   # verified: notify/models.py:44, :28
from datamodel import BaseModel, Column, Field             # verified: notify/models.py:9
from notify.conf import O365_CLIENT_ID, O365_CLIENT_SECRET, O365_TENANT_ID, O365_USER, O365_PASSWORD
    # verified: notify/conf.py:68-72
from notify.conf import NOTIFY_REDIS                        # verified: notify/conf.py:17
from notify.providers.teams._msgraph_patch import patch_graph_host_os_header  # verified: teams/_msgraph_patch.py:31
from notify.providers.office365 import Office365           # verified: notify/providers/office365/__init__.py:7
from notify.providers.outlook import Outlook               # verified: notify/providers/outlook/__init__.py:7
from notify import Notify                                  # verified: notify/server/wrapper.py:11
from redis import asyncio as aioredis                      # verified: notify/server/client.py:6
import aiofiles                                            # verified: notify/providers/outlook/outlook.py:7

# third-party (verified by import in the project .venv, 2026-09-15)
from msgraph import GraphServiceClient
    # __init__(credentials: Optional[Union[TokenCredential, AsyncTokenCredential]] = None,
    #          scopes: Optional[List[str]] = None, request_adapter: Optional[GraphRequestAdapter] = None)
    # .me -> UserItemRequestBuilder ; .users.by_user_id(id) -> UserItemRequestBuilder ; .request_adapter
from msgraph.generated.users.item.send_mail.send_mail_post_request_body import SendMailPostRequestBody
    # fields: message, save_to_sent_items
from msgraph.generated.models.message import Message
    # fields incl.: subject, body, from_, sender, to_recipients, cc_recipients, bcc_recipients, reply_to, importance, attachments
from msgraph.generated.models.item_body import ItemBody        # verified in use: teams.py:16
from msgraph.generated.models.body_type import BodyType        # verified in use: teams.py:17
from msgraph.generated.models.recipient import Recipient
from msgraph.generated.models.email_address import EmailAddress
from msgraph.generated.models.importance import Importance     # members: Low, Normal, High
from msgraph.generated.models.file_attachment import FileAttachment
    # fields incl.: name, content_type, content_bytes, content_id, is_inline
from msgraph.generated.models.attachment_item import AttachmentItem
    # fields: attachment_type, content_id, content_type, is_inline, name, size (+ odata_type, additional_data)
from msgraph.generated.models.attachment_type import AttachmentType
from msgraph.generated.users.item.messages.item.attachments.create_upload_session.create_upload_session_post_request_body import CreateUploadSessionPostRequestBody
from msgraph.generated.models.o_data_errors.o_data_error import ODataError
    # fields: error, message, response_status_code, response_headers
from msgraph_core.tasks.large_file_upload import LargeFileUploadTask
    # __init__(upload_session, request_adapter, stream: BytesIO, parsable_factory=None, max_chunk_size=5242880)
    # async upload(after_chunk_upload: Optional[Callable] = None)
from azure.core.credentials import AccessToken                 # namedtuple fields: token, expires_on
from azure.core.credentials_async import AsyncTokenCredential
    # get_token(self, *scopes, claims=None, tenant_id=None, enable_cae=False, **kwargs) -> AccessToken
import msal
    # ConfidentialClientApplication.acquire_token_on_behalf_of(user_assertion, scopes, claims_challenge=None, **kwargs)
    # ConfidentialClientApplication.acquire_token_for_client ; ClientApplication.__init__(…, token_cache=…)
    # PublicClientApplication.initiate_device_flow / acquire_token_by_device_flow
    # SerializableTokenCache().has_state_changed
from cryptography.fernet import Fernet                         # cryptography 46.0.7 (transitive via msal)
```

Request-builder attributes verified present: `UserItemRequestBuilder.send_mail`,
`UserItemRequestBuilder.messages`, `MessagesRequestBuilder.post(body: Message) -> Optional[Message]`,
`MessagesRequestBuilder.by_message_id`, `MessageItemRequestBuilder.send` (`SendRequestBuilder.post(request_configuration=None) -> None`),
`MessageItemRequestBuilder.attachments`, `AttachmentsRequestBuilder.create_upload_session`,
`SendMailRequestBuilder.post(body: SendMailPostRequestBody, request_configuration=None) -> None`,
`UsersRequestBuilder.by_user_id`.

Kiota's `AzureIdentityAccessTokenProvider` calls
`self._credentials.get_token(*scopes, claims=decoded_claim, enable_cae=self._is_cae_enabled[, **self._options])`
(verified in `kiota_authentication_azure/azure_identity_access_token_provider.py`), so
`MsalAsyncCredential.get_token` must accept `claims` and `enable_cae`.

Installed versions: `msgraph-sdk 1.22.0`, `msgraph-core 1.3.2`, `azure-identity 1.25.3`,
`azure-core 1.41.0`, `msal 1.32.0`, `cryptography 46.0.7`, `redis 5.2.1`, `aiofiles 24.1.0`
(the last two come through `navconfig[default]`), `o365 2.0.37`, `office365-rest-python-client 2.5.13`.

### Existing Class Signatures
```python
# notify/providers/base.py
class ProviderBase(ABC):                                         # line 31
    provider: str = None                                         # line 37
    provider_type: ProviderType = ProviderType.NOTIFY            # line 38
    blocking: bool = True                                        # line 39
    sent: Optional[Union[Callable, Awaitable]] = None            # line 40
    def __init__(self, *args, **kwargs): ...                     # line 42; pops "loop", "debug", "sent"; setattr loop lines 77-81
    async def __aenter__(self) -> "ProviderBase": ...            # line 84 → await self.connect()
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None: ...  # line 88 → await self.close()
    async def connect(self, *args, **kwargs): ...                # line 96 (abstract)
    async def close(self): ...                                   # line 100 (abstract)
    async def _prepare_(self, recipient: Actor = None, message: Union[str, Any] = None,
                        template: Optional[str] = None, template_is_source: Optional[bool] = None, **kwargs): ...
                                                                 # line 117; sets self._template (lines 155-166)
    async def _render_(self, to: Actor = None, message: str = None, subject: str = None, **kwargs): ...  # line 188
    async def _send_(self, to: Actor, message: Union[str, Any], subject: str = None, **kwargs) -> Any: ...  # line 209 (abstract)
    async def __sent__(self, recipient: Actor, message: str, result: Optional[Any], **kwargs): ...  # line 226; forwards **kwargs to self.sent
    async def send(self, recipient: list[Actor] = None, message: Union[str, Any] = None, subject: str = None, **kwargs): ...  # line 263

# notify/providers/mail.py
class ProviderEmail(ProviderBase, ABC):                          # line 15
    provider_type = ProviderType.EMAIL                           # line 22
    blocking: str = 'asyncio'                                    # line 23
    timeout: int = 60                                            # line 24
    def __init__(self, *args, **kwargs): ...                     # line 26
    async def close(self): ...                                   # line 36 (SMTP quit)
    async def connect(self, *args, **kwargs): ...                # line 47 (aiosmtplib)
    async def _render_(self, to: Actor = None, message: str = None, subject: str = None, **kwargs): ...  # line 104 (MIME)
    def add_attachment(self, message, filename, mimetype="octect-stream"): ...  # line 158
    async def _send_(self, to: Actor, message: str, subject: str, **kwargs): ...  # line 181
    async def send(self, recipient: list[Actor] = None, message: Union[str, Any] = None, subject: str = None, **kwargs):
        # line 209: connect() each call (224) wrapped in ProviderError (225-228); _prepare_ (232);
        # per-recipient _send_ tasks (240); exceptions → logger.warning, swallowed (246-249); __sent__(to, …, **kwargs) (251)

# notify/providers/office365/office365.py  (to be rewritten)
class Office365(ProviderEmail):                                  # line 34
    provider = "office365"                                       # line 41
    blocking: str = 'asyncio'                                    # line 42
    def __init__(self, *args, username: str = None, password: str = None, use_credentials: bool = True,
                 client_id: str = None, client_secret: str = None, tenant_id: str = None, **kwargs): ...  # line 44
    async def connect(self, **kwargs): ...                       # line 88
    async def close(self): ...                                   # line 153
    async def _render_(self, to: Actor, message: str = None, subject: str = None, **kwargs): ...  # line 156
    async def _send_(self, to: Actor, message: str, subject: str, **kwargs): ...  # line 190

# notify/providers/outlook/outlook.py  (to be rewritten)
class Outlook(ProviderEmail):                                    # line 22
    provider = "outlook"                                         # line 29
    def acquire_token(self): ...                                 # line 79  (removed)
    def acquire_token_by_username(self): ...                     # line 91  (removed)
    async def add_attachment(self, filename): ...                # line 103 (kept, new semantics M7)
    async def connect(self, **kwargs): ...                       # line 117
    async def _render_(…): ...                                   # line 136 — uses self.client.me.send_mail (153)
    async def _send_(…): ...                                     # line 164

# notify/providers/teams/teams.py
from ._msgraph_patch import patch_graph_host_os_header           # line 12
patch_graph_host_os_header()                                     # line 57
class Teams(ProviderIM):                                         # line 60
    def get_graph_client(self, client: Any, scopes: Optional[list] = None): ...  # line 88 → GraphServiceClient(credentials=client, scopes=scopes) (91)

# notify/providers/teams/_msgraph_patch.py
def patch_graph_host_os_header() -> bool: ...                    # line 31 (module-global _PATCHED at line 28)

# notify/models.py
class Account(BaseModel): ...                                    # line 28 (address: Union[str, list[str]], line 35)
class Actor(BaseModel): ...                                      # line 44 (name: str, account: Optional[Account])
class Attachment(BaseModel): ...                                 # line 96
class MailAttachment(Attachment): ...                            # line 129

# notify/notify.py
PROVIDERS = {}                                                   # line 10
class Notify:                                                    # line 18
    def __new__(cls, provider: str, *args, **kwargs): ...        # line 31

# notify/server/wrapper.py
class NotifyWrapper:                                             # line 18
    def __init__(self, provider: str, *args, **kwargs): ...      # line 40 — same kwargs later go to Notify(...) (71, 83) and send() (75, 87)

# notify/server/client.py
class NotifyClient:                                              # line 18
    async def publish(self, message: dict, channel: str): ...    # line 99  (json.dumps → redis.publish)
    async def stream(self, message: dict, stream: str, use_wrapper: bool = False): ...  # line 108 (NotifyWrapper(**message) / json → xadd)
    async def send(self, message: dict): ...                     # line 130 (json → TCP)

# notify/server/server.py
def build_notify(self, data: dict): ...                          # line 504 → NotifyWrapper(**msg) (507)

# notify/tests/base.py
class BaseTestCase:                                              # line 7 — autouse fixture calls component.connect()/close();
    # test_required_variables_on_connect asserts client_id/client_secret/tenant_id attributes exist
```

### Integration Points
| New Component | Connects To | Via | Verified At |
|---|---|---|---|
| `Office365` hooks | `ProviderEmail.send()` | class attrs `batch_recipients`, `raise_errors`, `redacted_send_kwargs` | `notify/providers/mail.py:209` |
| `Office365.__init__` | `ProviderBase.__init__` kwarg setattr | pop consumed kwargs before `super().__init__` | `notify/providers/base.py:77-81` |
| `Office365._render_` | `self._template.render_async` | template set by `_prepare_` | `notify/providers/base.py:155-166` |
| `MsalAsyncCredential` | `GraphServiceClient(credentials=…)` | Kiota calls `get_token(*scopes, claims=, enable_cae=)` | `msgraph/graph_service_client.py` (installed) |
| `GraphMailSender` | `graph.users.by_user_id(m)` / `graph.me` → `.send_mail.post` / `.messages…` | SDK request builders | verified by import (§6) |
| `LargeFileUploadTask` | `graph.request_adapter` | constructor arg | `msgraph_core/tasks/large_file_upload.py` (installed) |
| `RedisTokenStore` | `redis.asyncio.from_url` | same pattern as `NotifyClient.connect` | `notify/server/client.py:84` |
| `reject_queued_secrets` | `NotifyClient.publish/stream/send`, `NotifyWrapper.__init__` | first statement | `client.py:99,108,130`; `wrapper.py:40` |
| `teams` | `notify.providers._msgraph.patch_graph_host_os_header` | import change | `teams.py:12` |

### Does NOT Exist (Anti-Hallucination)
- ~~`azure.identity.aio.DeviceCodeCredential`~~: no async device-code credential (sync `azure.identity.DeviceCodeCredential` only). This spec uses MSAL device flow.
- ~~`azure.identity.aio.UsernamePasswordCredential`~~: sync only, and deprecated ("doesn't support multifactor authentication (MFA)").
- ~~Redis/custom backends in `azure.identity.TokenCachePersistenceOptions`~~: it only takes `allow_unencrypted_storage` and `name`.
- ~~`auth_flow_type="on_behalf_of"` in `O365.Connection`~~: O365 2.0.37 supports `authorization`, `public`, `credentials`, `certificate`, `password` only.
- ~~`msgraph.generated.me`~~ (module): does not exist. `GraphServiceClient.me` returns `msgraph.generated.users.item.user_item_request_builder.UserItemRequestBuilder`.
- ~~A `save_to_sent_items` option on `MessageItemRequestBuilder.send.post()`~~: draft sends take no body; a sent draft always goes to Sent Items.
- ~~Graph usage in the current `office365` provider~~: it is Outlook REST (`MSOffice365Protocol`), despite `docs/providers.rst`.
- ~~`notify/providers/_msgraph.py`, `notify/providers/office365/credential.py`, `token_store.py`, `graph_mail.py`, `login.py`~~: none exist yet (created by M1–M4, M8).
- ~~`MailSendResult`, `OutboundAttachment` in `notify/models.py`~~: not yet defined (M-models in §2).
- ~~`batch_recipients` / `raise_errors` / `redacted_send_kwargs` on `ProviderEmail`~~: not yet defined (M5).
- ~~`cc`, `bcc`, `reply_to`, `from_address`, `user_assertion`, `inline_images` handling in any email provider~~: none today.
- ~~`NotifyAuthError` in `notify/exceptions.pxd`~~: declared only in `exceptions.pyx:45`; do not `cimport` it.
- ~~`redis`, `aiofiles`, `cryptography` as direct entries in `pyproject.toml`~~: none are declared. `redis`/`aiofiles` come through `navconfig[default]`, `cryptography` through `msal`; M9 adds `cryptography` explicitly.
- ~~`pyo365` installed~~: listed in the `azure` extra (pyproject.toml:68) but not installed.
- ~~An offline test for `office365`~~: only `tests/test_outlook.py` / `tests/test_outlook1.py` exist; `examples/test_o365.py` is a manual script.
- ~~`tests/integration/`~~ directory: does not exist yet (M11 creates it).

---

## 7. Implementation Notes & Constraints

> Architecture decisions stay with the thinking model. A delegated
> implementation may only express a decision already recorded here and in
> the TASK's implementation blocks. It must never invent an API, choose a
> file, or resolve an open design question.

### Patterns to Follow
- **Never override `send()`** in `Office365`/`Outlook`. Behaviour comes from the M5 hooks and
  `_send_` (`.claude/rules/codebase-conventions.md`).
- Graph client construction follows `Teams.get_graph_client` (teams.py:88-91). Call
  `patch_graph_host_os_header()` once when the module loads, as teams.py:57 does.
- Settings come only from `notify/conf.py` (navconfig); no `os.environ` in providers. Log with
  `self.logger`; no `print` except in the CLI's stderr output (M8).
- New data structures are datamodel `BaseModel`s in `notify/models.py`, never bare dicts
  (`MailSendResult`, `OutboundAttachment`).
- MSAL is sync, so every call goes through `loop.run_in_executor`. Graph is async `msgraph-sdk`.
  Attachments are read with `aiofiles`.
- Secrets hygiene: never log or embed assertions, client secrets, certificate passwords, tokens or
  cipher keys. Mask mailbox addresses only if asked (addresses are not secrets).
- Tests mock `GraphServiceClient` and MSAL; no network in unit tests. `asyncio_mode = auto`
  (pytest.ini).
- No `.pyx` change is needed, so no Cython rebuild is required by this feature (worktrees still
  need `python setup.py build_ext --inplace` before tests, per worktree rules).

### Known Risks / Gotchas
- **`ProviderBase.__init__` copies unknown kwargs onto `self`** (base.py:77-81): pop every consumed
  kwarg, or secrets such as `client_certificate_password` end up as public attributes.
- **`ProviderEmail.send()` calls `connect()` every send** (mail.py:224), and so does `__aenter__`:
  `connect()` must be idempotent and cheap.
- **Secrets through `sent` callbacks**: `__sent__` forwards `**kwargs` (base.py:226-251). Covered
  by `redacted_send_kwargs`.
- **Notify server**: `NotifyWrapper` reuses the same kwargs for both the constructor and `send()`
  (wrapper.py:71-87), and payloads travel through Redis/cloudpickle. Covered by M10 rejection; OBO
  is **direct send only**.
- **Expired or invalid assertion** (`invalid_grant`, `AADSTS50013`, `AADSTS65001` missing consent)
  → `NotifyAuthError`. Never retry in a loop. The caller must obtain a fresh user token.
- **OBO tenant prerequisites**: the incoming token's `aud` must be this app (an exposed API scope).
  The app needs delegated `Mail.Send` (+ `Mail.Send.Shared` for shared mailboxes) with consent, and
  it must be a confidential client (secret/certificate). Document these; surface MSAL's
  `error_description` without secrets.
- **Delegated device code** needs "Allow public client flows" on the app registration. Conditional
  Access may block it; the error is surfaced.
- **ROPC** fails with MFA or federated accounts. The error must point to `delegated` + the login
  CLI.
- **App-only over-reach**: application `Mail.Send` can send as any mailbox. Document Exchange
  Application Access Policy / RBAC for Applications scoping.
- **Behaviour change in flow defaults**: `use_credentials` used to default to `True` (ROPC/basic).
  It now defaults to `None`, so a caller with client secret settings and no explicit
  `use_credentials=True` is resolved to `client_credentials`, and app-only then **requires**
  `sender`/`from_address`. Call this out in release notes.
- **Removed API**: `Outlook.acquire_token()` / `acquire_token_by_username()` are gone, and
  `.o365_token.txt` is no longer read. Release notes must say so.
- **Template context change**: with `batch_recipients`, `recipient`/`username` in templates is the
  **list** of `Actor`s, not one `Actor`. Existing office365/outlook templates that use
  `recipient.name` must change. Release notes must say so.
- **Token cache blob concurrency**: several workers writing the same Redis key are last-writer-wins.
  MSAL re-acquires missing tokens, so this is acceptable (at worst an extra token request). Keep
  one cache key per `tenant:client:flow`.
- **Growth of the OBO cache blob**: many users make the serialized cache grow. Use the Redis TTL
  (`O365_TOKEN_STORE_TTL`) or leave OBO on the memory store. Documented.
- **Draft strategy and Sent Items**: a draft send always saves to Sent Items; warn when
  `save_to_sent_items=False`. A failed upload or send leaves a draft behind, so delete it best
  effort.
- **Graph limits**: roughly 3 MB inline request, 150 MB per upload-session file, 5 MiB default
  upload chunk; 429 `Retry-After` is handled by msgraph-core retry middleware (default handler
  chain).
- **HostOs header bug** in msgraph-core: the patch must run before the first request (module import
  of `office365.py`).
- **`BaseTestCase`** (notify/tests/base.py) calls the real `connect()` in an autouse fixture and
  expects `authenticate` to be True in `test_authenticate`. The rewritten outlook tests either stop
  using it or set `authenticate = True` after a successful `connect()`; decide in M11 without
  network access.
- **Mixed-list addresses**: `Account.address` may be a list (models.py:35); `to_recipients` must
  flatten it.
- **Tooling note**: `reserve_ids.py` printed `FEAT-4`, but its own `_FEATURE_ID_RE` requires ≥3
  digits (`reserve_ids.py:417`), so this spec uses the zero-padded `FEAT-004` (same number, matches
  FEAT-001..003).

### External Dependencies
| Package | Version | Reason |
|---|---|---|
| `msgraph-sdk` | `>=1.22.0` (installed 1.22.0) | Graph client, typed mail models, request builders |
| `msgraph-core` | `>=1.3.2` (installed 1.3.2) | `LargeFileUploadTask`, retry middleware |
| `msal` | `>=1.32.0` (installed 1.32.0) | all token flows plus `SerializableTokenCache` |
| `azure-identity` | `>=1.23.0` (installed 1.25.3) | kept (teams uses it); brings `azure-core` (`AccessToken`, `AsyncTokenCredential`) |
| `cryptography` | `>=42.0` (installed 46.0.7) | Fernet token encryption; **added explicitly** to `azure`/`all` |
| `redis` (async) | via `navconfig[default]` (5.2.1) | Redis token store |
| `aiofiles` | via `navconfig[default]` (24.1.0) | async attachment reads |
| ~~`o365`~~, ~~`pyo365`~~, ~~`Office365-REST-Python-Client`~~ | — | **removed** |

---

## Worktree Strategy

- **Default isolation unit**: `per-spec`. All tasks run sequentially in one worktree
  (`feat-FEAT-004-mail-messages-graph`, branched from `origin/dev`).
- **Why**: M3 ↔ M4 ↔ M6 share an internal contract (credential ↔ Graph client ↔ provider), and
  M9 (`conf.py`, `pyproject.toml`) is touched by several modules, so parallel worktrees would
  churn merges.
- **Suggested order**: M1 → M9 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → M10 → M11. M1, M2, M5 and M10
  have no dependencies on each other and could be split later if needed.
- **Cross-feature dependencies**: none open. FEAT-001 (NAV-8390 email-utf8), FEAT-002
  (templateparser-refactor) and FEAT-003 (jinja-string-notify) are merged on `dev`. M5 edits
  `notify/providers/mail.py`, which FEAT-001 last changed, so rebase on `dev` before starting.

---

## 8. Open Questions

- [x] Flow type and base branch? — *Resolved in brainstorm*: `type: feature`, `base_branch: dev`.
- [x] What does "on behalf of" mean? — *Resolved in brainstorm*: both send-as / from another mailbox **and** the OAuth2 OBO token flow.
- [x] Which provider gets Graph support? — *Resolved in brainstorm*: rewrite `office365` on Graph (keep the name).
- [x] Which auth flows must work? — *Resolved in brainstorm*: client credentials, OBO user assertion, delegated with cached token, username/password (ROPC).
- [x] How does the OBO user token reach the provider? — *Resolved in brainstorm*: per-send kwarg (`user_assertion=`), per-user token cache, one instance for many users.
- [x] Token storage? — *Resolved in brainstorm*: pluggable, in-memory default, file/Redis backends.
- [x] Backward compatibility? — *Resolved in brainstorm*: keep constructor kwargs, add `auth_flow`, warn on legacy (ROPC); remove the `input()` flow.
- [x] Launch mail features? — *Resolved in brainstorm*: attachments incl. >3 MB, CC/BCC/Reply-To, save-to-sent-items control, inline CID images.
- [x] What happens to `outlook` / `Office365-REST-Python-Client`? — *Resolved in brainstorm*: package is broken and must be replaced completely by ms-graph (`msgraph-sdk`); `outlook` moves onto the same Graph core.
- [x] Delegated bootstrap method? — *Resolved in brainstorm*: device code.
- [x] Send-as mailbox source? — *Resolved in brainstorm*: instance default (`sender=`) overridable per send (`from_address=`), for app-only and delegated/OBO.
- [x] Live test tenant available? — *Resolved in brainstorm*: yes, an existing Entra ID tenant for `@pytest.mark.integration` tests.
- [x] One Graph message to all recipients, or one per recipient? — *Resolved at spec time (Jesus Lara)*: **one message to all** (M5 `batch_recipients`, AC6).
- [x] How do Graph failures surface? — *Resolved at spec time (Jesus Lara)*: **raise auth/config errors** (`NotifyAuthError`); other failures return `MailSendResult` (M4, M5 `raise_errors`, AC9).
- [x] OBO jobs through the notify server? — *Resolved at spec time (Jesus Lara)*: **reject** `user_assertion` in queued jobs (M10, AC14).
- [x] Certificate-based client credentials at launch? — *Resolved at spec time (Jesus Lara)*: **yes** (M3, AC2).
- [x] Drop `o365` / `pyo365` from extras? — *Resolved at spec time (Jesus Lara)*: **yes**, together with `Office365-REST-Python-Client` (M9, AC17).
- [x] Redis token store security? — *Resolved at spec time (Jesus Lara)*: **encrypted** (Fernet key from navconfig); plaintext only with explicit `allow_unencrypted=True` (M2, AC5). Same rule applied to the file store.
- [x] Move `_msgraph_patch.py` to a shared module? — *Resolved at spec time (Jesus Lara)*: **yes**, `notify/providers/_msgraph.py` with a teams shim (M1, AC15).
- [x] Where does the device-code bootstrap live? — *Resolved at spec time (Jesus Lara)*: `python -m notify.providers.office365.login` (M8, AC16).
- [ ] Should `outlook` also log a `DeprecationWarning` pointing to `office365`, or stay a silent alias? (Spec default: silent alias.) — *Owner: Jesus Lara*
- [ ] Target version: `1.7.0` (minor, behaviour changes plus removed extras) or `2.0.0` given the template-context and flow-default changes in §7? — *Owner: Jesus Lara*
- [ ] Integration-test OBO helper: how does the live test obtain a user assertion for the exposed API scope (a ROPC test account in the test tenant, or a pre-issued token in navconfig)? — *Owner: Jesus Lara*
- [ ] Should the rewritten outlook tests keep inheriting `notify/tests/base.py::BaseTestCase` (which calls the real `connect()` and checks `authenticate`) or move to plain fixtures? — *Owner: implementer (M11)*

---

## 9. Design Research Cross-Check

> Independent design opinion from the `codex` seat over the **accepted exploration
> doc** (never over this spec). Model: `gpt-5.6-luna` · Status: skipped (brainstorm
> `sdd/proposals/mail-messages-graph.brainstorm.md` has `Status: exploration`, not `accepted`)
> · Transcript: —

| # | Suggestion (kind) | Disposition | Reason | Landed in |
|---|---|---|---|---|

Summary: **0** confirmed · **0** rejected · **0** escalated.

---

## Revision History

| Version | Date | Author | Change |
|---|---|---|---|
| 0.1 | 2026-09-15 | Jesus Lara | Initial draft from brainstorm (Option B) plus spec-time decisions (fan-out, errors, queue OBO, scope) |
