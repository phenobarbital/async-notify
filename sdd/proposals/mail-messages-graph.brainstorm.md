---
# SDD flow type and base branch (FEAT-145).
# - type: feature  (default)  → base_branch: dev (or any non-main branch)
# - type: hotfix              → base_branch MUST be: main
type: feature
base_branch: dev
---

# Brainstorm: Mail Messages via Microsoft Graph (send-as & On-Behalf-Of)

**Date**: 2026-09-15
**Author**: Jesus Lara
**Status**: exploration
**Recommended Option**: B

---

## Problem Statement

The question was: can the `office365` provider send email through **Microsoft Graph**, and can it
send **"on behalf of"** someone else? Right now it can't do either properly.

1. **`office365` does not use Graph.** `notify/providers/office365/office365.py` builds on the
   `O365` library with `MSOffice365Protocol` and the scope `https://outlook.office.com/.default`,
   which is the legacy Outlook REST API, not Graph. `o365` is pinned `<2.1` in `pyproject.toml`
   because 2.1 removed `MSOffice365Protocol`, so the provider has no upgrade path. On first run it
   calls `print()` and `input()` to get an authorization URL, which cannot work in a server, worker
   or the notify server. If authentication fails it deletes `.o365_token.txt` and calls itself
   again with no limit. The `use_credentials=True` path builds a `Message(auth=(user, password))`,
   which is basic auth that Exchange Online no longer accepts. `docs/providers.rst` wrongly says it
   uses the Graph API.
2. **`outlook` uses a broken library.** `notify/providers/outlook/outlook.py` uses
   `Office365-REST-Python-Client` (`office365.graph_client.GraphClient`). The user confirmed the
   package is broken and must be **removed completely**. The provider also sends with
   `client.me.send_mail(...)`, and `/me` does not work with an app-only (client-credentials) token.
3. **No "on behalf of" support.** Neither provider can:
   - send **as another mailbox** (a shared mailbox such as `noreply@`, or another user) by setting
     Graph's `from`/`sender` fields or calling `POST /users/{mailbox}/sendMail`, or
   - use the **OAuth2 On-Behalf-Of (OBO)** flow, where a middle-tier service (for example a
     navigator/aiohttp app) receives a signed-in user's access token and exchanges it for a Graph
     token, so mail is sent *as that user*.

**Who is affected**: developers who send transactional or templated email through
`Notify("office365")` / `Notify("outlook")`, the notify server workers (unattended, multi-user), and
operators who today have to bootstrap tokens by hand.

**Why now**: the `o365` pin has no way forward, the Outlook REST backend is legacy, the REST client
is broken, and product flows need to send mail as the signed-in user or from shared mailboxes.

## Constraints & Requirements

Decisions from discovery (Rounds 0–3):

- **Flow**: `type: feature`, `base_branch: dev`.
- **Target**: rewrite **`office365`** on Microsoft Graph and keep its name.
- **`Office365-REST-Python-Client` must be removed completely** (user: "this package is broken").
  `outlook` moves onto the same Graph core. Neither provider may import it any more.
- **Graph library**: `msgraph-sdk` (user: "replaced by ms-graph"). It is already a dependency
  (`msgraph-sdk>=1.22.0`, `msgraph-core>=1.3.2`, `azure-identity>=1.23.0` in the `azure` and `all`
  extras) and is already used by the `teams` provider.
- **"On behalf of" means both**:
  - **send-as / from another mailbox**, and
  - the **OAuth2 OBO token flow**.
- **Auth flows that must work**:
  1. client credentials (app-only; client secret, optionally a certificate),
  2. OBO user assertion,
  3. delegated with a cached token, bootstrapped once by **device code** (the `input()` flow is
     removed),
  4. username/password (ROPC). Kept for backward compatibility only, and logs a
     `DeprecationWarning`.
- **OBO input**: a **per-send kwarg** (`send(..., user_assertion=<jwt>)`). One provider instance
  must be able to serve many users, with exchanged tokens cached per user.
- **Token cache**: **pluggable**, **in-memory by default**, with file and Redis backends (the notify
  server already runs Redis). No more implicit `.o365_token.txt` in `BASE_DIR`.
- **Send-as mailbox**: an instance default (`sender=`) that each send can override
  (`from_address=`). Works with app-only (`/users/{from}/sendMail`) and with delegated or OBO tokens
  (the user needs SendAs or SendOnBehalf rights on the target mailbox).
- **Backward compatibility**: keep the existing constructor kwargs (`username`, `password`,
  `use_credentials`, `client_id`, `client_secret`, `tenant_id`) and add an explicit `auth_flow`.
  Legacy paths warn instead of breaking.
- **Mail features at launch**: attachments, including large ones (>3 MB) through Graph upload
  sessions; CC/BCC/Reply-To (and importance); a `save_to_sent_items` switch; inline CID images in
  HTML templates.
- **Project conventions** (`.claude/rules/codebase-conventions.md`): async-first with no blocking
  I/O in coroutines, settings come from `notify/conf.py` (navconfig) and never `os.environ`,
  `self.logger` instead of `print`, Google-style docstrings with strict type hints, and datamodel
  `BaseModel` for new data structures.
- **Testing**: offline unit tests with a mocked transport are required. A **real Entra ID tenant
  exists**, so `@pytest.mark.integration` live tests (app-only, send-as to a shared mailbox, OBO,
  device-code cache reuse) can be written and gated on navconfig credentials.
- **Security**: user assertions and refresh tokens are secrets. They must never be logged, never
  passed to `sent` callbacks, and never written to Redis streams in plain text.

---

## Options Explored

### Option A: msgraph-sdk + native `azure-identity` async credentials

Rebuild `office365` on `GraphServiceClient`. For each flow, use the matching `azure-identity`
credential:
`azure.identity.aio.ClientSecretCredential` / `CertificateCredential` (app-only),
`azure.identity.aio.OnBehalfOfCredential(user_assertion=...)` (OBO),
`azure.identity.DeviceCodeCredential` (delegated) and `azure.identity.UsernamePasswordCredential`
(ROPC). Each OBO user gets its own credential and Graph client, kept in a small LRU. Mail is sent
with `users.by_user_id(mailbox).send_mail.post(SendMailPostRequestBody(...))`. `outlook` becomes a
subclass/alias. This is the pattern `teams` already follows (`teams.py:7-11`, `:88-91`).

✅ **Pros:**
- Least custom auth code: Microsoft maintains the credentials, including token refresh.
- Matches the existing `teams` provider, so reviewers already know the pattern.
- `OnBehalfOfCredential` and `ClientSecretCredential` are **natively async** (verified in
  `azure.identity.aio`).

❌ **Cons:**
- **No pluggable or Redis token cache.** `azure-identity` only persists through
  `TokenCachePersistenceOptions` (msal-extensions: file or OS keyring). That misses the "pluggable,
  Redis" requirement, so delegated tokens would not be shared between notify-server workers.
- `DeviceCodeCredential` and `UsernamePasswordCredential` are **sync only** (no `aio` variant,
  verified), so they need a sync-to-async shim. `UsernamePasswordCredential` already emits a
  deprecation warning in azure-identity 1.25.3.
- A credential object *and* a `GraphServiceClient` (httpx client, Kiota adapter) per OBO user is
  heavy. The per-user cache is in-process only, and exchanged OBO tokens are lost on restart.
- Two different token-cache models (azure-identity internal cache vs msal-extensions file) make
  behaviour hard to predict.

📊 **Effort:** Medium

📦 **Libraries / Tools:**
| Package | Purpose | Notes |
|---|---|---|
| `msgraph-sdk` | Graph client, typed `Message`/`FileAttachment` models, `sendMail`, upload sessions | 1.22.0 installed; already a dependency |
| `msgraph-core` | `LargeFileUploadTask`, Graph middleware | 1.3.2 installed; needs the HostOs header patch |
| `azure-identity` | Async credentials (secret, certificate, OBO) plus sync device code / ROPC | 1.25.3 installed |

🔗 **Existing Code to Reuse:**
- `notify/providers/teams/teams.py` — `GraphServiceClient(credentials=..., scopes=...)` and
  `ClientSecretCredential` wiring.
- `notify/providers/teams/_msgraph_patch.py` — `patch_graph_host_os_header()`, required by every
  Graph-based provider.
- `notify/providers/mail.py` — `ProviderEmail` base (templating, the `send()` fan-out).

---

### Option B: msgraph-sdk + MSAL-backed unified async credential with pluggable token cache ⭐

Also rebuild `office365` on `GraphServiceClient`, but put **one auth layer** in front of it:
an `AsyncTokenCredential` adapter (it implements `get_token()` / `close()` and is passed to
`GraphServiceClient(credentials=...)`) backed by **MSAL**, with a single `msal.SerializableTokenCache`
whose serialized state lives in a **pluggable token store** (memory by default, file, Redis).

All four flows go through MSAL, which supports each of them (verified in msal 1.32.0):
- app-only → `ConfidentialClientApplication.acquire_token_for_client`
- OBO → `ConfidentialClientApplication.acquire_token_on_behalf_of(user_assertion, scopes)`. MSAL
  caches the result per user assertion and refreshes it silently.
- delegated → `PublicClientApplication.initiate_device_flow` / `acquire_token_by_device_flow` once,
  through a bootstrap helper, then `acquire_token_silent` with the cached refresh token.
- ROPC (legacy) → `acquire_token_by_username_password`, with a `DeprecationWarning`.

MSAL is synchronous, so each token acquisition runs in `loop.run_in_executor` (a rare, cache-first
call). The Graph HTTP calls stay fully async in `msgraph-sdk`. Which user's token to use (OBO) is
decided per send, so **one `GraphServiceClient` per provider instance** can serve many users. A
shared Graph mail core (message builder, recipients, attachments with upload sessions, CID
images, send-as routing) lives next to the provider, and `outlook` becomes a thin alias of it.

✅ **Pros:**
- **Meets every auth requirement with one cache model**: app-only, OBO, device code and ROPC all
  share one `SerializableTokenCache` that can be stored in memory, a file or Redis. notify-server
  workers can then share delegated refresh tokens and OBO results.
- MSAL's OBO cache already handles "many users, one app" (keyed by assertion) and refreshes tokens,
  so there is no per-user credential or client object.
- One `GraphServiceClient` per provider instance: one connection pool, cheap per-send switching.
- Device-code bootstrap works on headless servers and **removes `input()`** from the send path.
- Keeps `msgraph-sdk` typed models and `LargeFileUploadTask` for >3 MB attachments.

❌ **Cons:**
- More custom code than Option A: the credential adapter and the token-store interface have to be
  written and tested.
- MSAL calls are sync and must go through the executor. They hit the network only on cache misses.
- The token store holds refresh tokens, so a Redis store needs encryption at rest or an explicit
  opt-in, plus a documented TTL/eviction policy.
- Per-send user selection has to be concurrency-safe, because `send()` fans recipients out with
  `asyncio.as_completed` (for example a `contextvars.ContextVar` set inside `_send_`, or resolving
  the token before building the request).

📊 **Effort:** Medium–High

📦 **Libraries / Tools:**
| Package | Purpose | Notes |
|---|---|---|
| `msgraph-sdk` | Graph client and typed mail models | 1.22.0 installed |
| `msgraph-core` | `LargeFileUploadTask` (5 MiB default chunks) | 1.3.2 installed; HostOs patch required |
| `msal` | All token flows plus `SerializableTokenCache` | 1.32.0 installed; sync → executor |
| `azure-core` | `AccessToken` / `AsyncTokenCredential` protocol used by Kiota's auth provider | 1.41.0 installed (transitive) |
| `redis` (async) | Optional Redis token store | already used by `notify/server/` |

🔗 **Existing Code to Reuse:**
- `notify/providers/teams/teams.py:88-91` — `get_graph_client()` construction pattern.
- `notify/providers/teams/_msgraph_patch.py:31` — `patch_graph_host_os_header()`.
- `notify/providers/mail.py:15` — `ProviderEmail` (templates through `self._template.render_async`,
  the recipient fan-out in `send()` at `:209`).
- `notify/conf.py:68-72` — existing `O365_*` settings, extended with the new keys.
- `notify/server/` — the existing Redis connection settings, for the Redis token store.

---

### Option C: Thin native aiohttp Graph REST client + MSAL (no msgraph-sdk)

Skip the SDK. Call `POST https://graph.microsoft.com/v1.0/users/{mailbox}/sendMail` (and
`/messages`, `/attachments/createUploadSession`) directly with `aiohttp` and a JSON payload. Tokens
come from the same MSAL + pluggable cache layer as Option B.

✅ **Pros:**
- Uses `aiohttp`, which `codebase-conventions.md` prefers. No httpx/Kiota stack and no HostOs
  telemetry monkeypatch.
- Very light, fully under project control, and the payload is easy to mock in tests.
- The `azure` extra could shrink for users who only need mail.

❌ **Cons:**
- **Goes against the user's explicit direction** to use ms-graph (`msgraph-sdk`).
- Upload-session chunking, retry/throttling (429 `Retry-After`), and OData error parsing all have
  to be reimplemented. `msgraph-core` middleware already handles them.
- Two Graph client styles in one repo (`teams` on the SDK, mail on raw REST).

📊 **Effort:** Medium

📦 **Libraries / Tools:**
| Package | Purpose | Notes |
|---|---|---|
| `aiohttp` | HTTP transport | already a core dependency |
| `msal` | Token flows and cache | 1.32.0 |

🔗 **Existing Code to Reuse:**
- `notify/providers/teams/teams.py` — existing aiohttp usage for webhooks.
- `notify/providers/mail.py` — `ProviderEmail`.

---

### Option D (unconventional): SMTP AUTH with OAuth2 (XOAUTH2) on the existing SMTP stack

Keep email on `ProviderEmail`/`aiosmtplib` (`smtp.office365.com:587`) and replace the password with
an OAuth2 token for the scope `https://outlook.office.com/SMTP.Send` (delegated) or the app-only
`.default`, sent as SASL `XOAUTH2`. Messages are built with the existing UTF-8-safe MIME helpers
(`_mime_utils`, NAV-8390), so inline CID images and attachments work unchanged. Send-as works by
setting the `From` header, which needs the SendAs right.

✅ **Pros:**
- Reuses the most existing code: MIME assembly, RFC 2047/2231 encoding, attachment and CID
  handling are already written and tested.
- No Graph payload limits on attachments (only the SMTP message size limit).
- Tokens still come from MSAL, so OBO and device code are possible in principle.

❌ **Cons:**
- **Not Microsoft Graph**, which fails the core question of this brainstorm.
- **SMTP AUTH is disabled by default** in many Exchange Online tenants. App-only SMTP also needs the
  service principal registered in Exchange (`New-ServicePrincipal`) and mailbox permissions, which
  means more tenant setup.
- No `saveToSentItems` control, and Microsoft is steering customers away from SMTP AUTH to Graph.
- `aiosmtplib` has no built-in XOAUTH2, so a custom `AUTH` exchange is needed.

📊 **Effort:** Medium

📦 **Libraries / Tools:**
| Package | Purpose | Notes |
|---|---|---|
| `aiosmtplib` | SMTP transport | already a core dependency |
| `msal` | OAuth2 tokens for SMTP scope | 1.32.0 |

🔗 **Existing Code to Reuse:**
- `notify/providers/mail.py:47` — `ProviderEmail.connect()` (aiosmtplib + TLS context).
- `notify/providers/_mime_utils.py` — `build_alternative_message`, `attach_text_part`,
  `attach_file`, `format_address`.

---

## Recommendation

**Option B** is recommended because:

- It is the **only option that meets every stated requirement**: Graph through `msgraph-sdk` (the
  user's direction), all four auth flows, OBO as a per-send kwarg serving many users from one
  instance, and a **pluggable memory/file/Redis token cache**. Option A cannot store tokens in Redis
  and would duplicate credential and client objects per OBO user. Option C ignores the SDK
  direction. Option D is not Graph.
- MSAL's own OBO cache (keyed by assertion, refreshed silently) is exactly what a multi-user worker
  needs, so no per-user credential or client registry has to be built.
- One `GraphServiceClient` per provider keeps connection reuse, and all mail-building code (typed
  `Message`, `FileAttachment`, `LargeFileUploadTask`) comes from the SDK.

**Trade-offs accepted**: a small custom `AsyncTokenCredential` adapter plus a token-store
interface (more code than Option A), and MSAL token calls going through the executor. That is
acceptable because they run only on cache misses; the actual send path stays async. The msgraph
HostOs monkeypatch is inherited from `teams` and has to stay until upstream fixes it.

---

## Feature Description

### User-Facing Behavior

**App-only (daemon/worker), sending as a shared mailbox:**
```python
mail = Notify("office365", auth_flow="client_credentials", sender="noreply@contoso.com")
async with mail as m:
    await m.send(recipient=[actor], subject="Hi", template="welcome.html",
                 cc=["ops@contoso.com"], attachments=["/tmp/report.pdf"])
```

**OBO from a web request handler (sends as the signed-in user):**
```python
mail = Notify("office365", auth_flow="on_behalf_of")          # long-lived, shared
await mail.send(recipient=actor, subject="Approved", message=html,
                user_assertion=request_bearer_token)            # per send
# optional: from_address="team@contoso.com" (needs SendAs/SendOnBehalf rights)
```

**Delegated (device code, one-time bootstrap):** a helper / CLI entry point prints the
verification URL and code, the user signs in once, and the refresh token is saved to the configured
token store. After that, `Notify("office365", auth_flow="delegated", username="me@contoso.com")`
sends silently.

**Legacy usage keeps working:** `Notify("office365", use_credentials=True)` maps to ROPC and logs a
`DeprecationWarning`. `Notify("outlook", ...)` keeps working as an alias of the new core.

Send-level kwargs: `cc`, `bcc`, `reply_to`, `importance`, `save_to_sent_items`, `attachments`
(paths or `MailAttachment`), `inline_images` (CID → path/bytes), `from_address`,
`user_assertion`.

### Internal Behavior

1. **Configuration**: `notify/conf.py` gains `O365_AUTH_FLOW`, `O365_SENDER`,
   `O365_CLIENT_CERTIFICATE` (path/thumbprint), `O365_TOKEN_STORE` (`memory|file|redis`) and its
   store settings. Existing `O365_CLIENT_ID/SECRET/TENANT_ID/USER/PASSWORD` stay.
2. **Constructor**: decides `auth_flow` from an explicit kwarg or setting, otherwise from legacy
   kwargs (`use_credentials=True` → ROPC with a warning; client id + secret → client credentials).
   It checks that the flow has the inputs it needs (OBO and client credentials need a secret or
   certificate; device code and ROPC need a public-client app). The `input()`/`print()` flow and the
   recursive retry are removed.
3. **Token layer**: a token-store interface with in-memory (default), file and Redis
   implementations, holding the serialized `msal.SerializableTokenCache`. An MSAL-backed
   `AsyncTokenCredential` gets tokens cache-first, calls MSAL in the executor, and writes the cache
   back only when it changed. For OBO, it chooses the token for the assertion attached to the
   current send.
4. **Graph client**: one `GraphServiceClient(credentials=<adapter>, scopes=[".default" or delegated
   Mail.Send scopes])` per provider instance, created once in `connect()`. It must stay
   **idempotent**, because `ProviderEmail.send()` calls `connect()` on every send and `__aenter__`
   calls it too. `patch_graph_host_os_header()` is applied when the module loads.
5. **Message building** (shared Graph mail core): renders the body through the existing template
   path, builds `Message` with `to_recipients`/`cc_recipients`/`bcc_recipients`/`reply_to`/
   `importance`/`from_`, adds inline `FileAttachment(is_inline=True, content_id=...)` for CID images
   and small attachments, and picks a strategy:
   - total size under the inline limit → `POST /users/{mailbox}/sendMail` with
     `save_to_sent_items`;
   - otherwise → create a draft in the mailbox, upload each large file with
     `createUploadSession` + `LargeFileUploadTask`, then `POST /messages/{id}/send`.
6. **Send-as routing**: the mailbox is `from_address` or `sender` or, for delegated/OBO, the token's
   user (`/me`). App-only always calls `/users/{mailbox}`, never `/me`. For delegated/OBO sends from
   a different mailbox, set `from_` (with SendAs rights the mail appears from that mailbox; with
   SendOnBehalf it shows "user on behalf of mailbox").
7. **Result and errors**: map `ODataError` codes (e.g. `ErrorSendAsDenied`, `ErrorAccessDenied`,
   `MailboxNotEnabledForRESTAPI`, 429 throttling) to `ProviderError` / `NotifyAuthError` with clear
   messages. Tokens and assertions never appear in log output.
8. **`outlook`**: becomes a thin subclass/alias of the new core. `Office365-REST-Python-Client`
   (and `pyo365`, plus `o365` once nothing imports it) are removed from `pyproject.toml` extras.

### Edge Cases & Error Handling

- **Recipient fan-out vs CC/BCC**: `ProviderEmail.send()` calls `_send_` once **per recipient**.
  CC/BCC would then be copied into every message. The spec must decide between one message to all
  recipients and per-recipient messages (the current behaviour), and CC/BCC must follow that choice.
- **Swallowed errors**: `ProviderEmail.send()` (`mail.py:242-249`) logs a warning when `_send_`
  raises and leaves the failure out of `results`. Graph auth or permission errors would be silent
  unless the rewrite surfaces them (overriding `send()` is forbidden, so this goes through result
  objects or a strict mode).
- **Token leakage**: `send()` forwards `**kwargs` to `__sent__` and on to the user `sent` callback
  (`base.py:226-251`). `user_assertion` must be removed before that. `ProviderBase.__init__` also
  copies unknown kwargs onto `self` (`base.py:77-81`), so a constructor-level `user_assertion` would
  stay on the instance. Reject it or store it privately.
- **notify server**: `notify/server/wrapper.py:40-87` passes the same kwargs to the `Notify(...)`
  constructor *and* to `send()`, and jobs travel through Redis. OBO assertions expire (about 1 hour)
  and are secrets, so queued OBO jobs need a policy: reject, encrypt, or require immediate send.
- **Expired or invalid assertion**: MSAL returns `invalid_grant`. Surface it as `NotifyAuthError`
  (the caller must get a fresh user token). Never retry forever.
- **Assertion audience**: OBO works only if the incoming token's `aud` is this app registration
  (an exposed API scope) and the app has consented delegated `Mail.Send` (and `Mail.Send.Shared`
  for shared mailboxes). Report the misconfiguration clearly (`AADSTS50013` / `AADSTS65001`).
- **MFA / Conditional Access**: ROPC fails, so give a clear error that points to device code.
  Conditional Access `claims` challenges on OBO must be reported, not swallowed.
- **App-only over-reach**: application `Mail.Send` can send as *any* mailbox in the tenant. Document
  the Exchange Online Application Access Policy / RBAC for Applications scoping.
- **Attachments**: Graph limits inline `sendMail` payloads (roughly 3–4 MB), so larger files go
  through upload sessions (up to 150 MB per file). Enforce the limits before upload, detect MIME
  type, and handle missing files (`FileNotFoundError`, as `outlook.add_attachment` does today).
- **Inline images**: a CID referenced in HTML without a matching attachment gets a warning. Inline
  attachments count toward the size strategy.
- **Throttling**: 429 / `MailboxConcurrency` responses follow `Retry-After` through the msgraph-core
  retry middleware.
- **Token store failures**: if Redis is down, fall back to in-memory with a warning, never block the
  send. A corrupt serialized cache is discarded and the flow re-authenticates (device code cannot
  re-authenticate unattended, so it raises a clear error).
- **Device code timeout** in the bootstrap helper: exit cleanly with a message. The send path never
  starts an interactive login.
- **UTF-8**: subjects and bodies are JSON, so the NAV-8390 MIME concerns do not apply to Graph.
  Non-ASCII names in `EmailAddress.name` must still round-trip.

---

## Capabilities

### New Capabilities
- `graph-mail-transport`: Microsoft Graph `sendMail` / draft + send pipeline on `msgraph-sdk`
  (recipients, CC/BCC/Reply-To, importance, save-to-sent-items).
- `graph-mail-attachments`: small attachments inline, large attachments through upload sessions,
  CID inline images.
- `msal-async-credential`: an MSAL-backed `AsyncTokenCredential` for client credentials, OBO,
  delegated (silent refresh) and legacy ROPC.
- `pluggable-token-store`: token cache persistence interface with memory, file and Redis backends.
- `graph-send-as`: routing a send through another mailbox (`sender` / `from_address`) for app-only,
  delegated and OBO.
- `device-code-bootstrap`: a headless one-time delegated sign-in helper that seeds the token store.

### Modified Capabilities
- `office365-provider`: rewritten from the O365 Outlook-REST backend to Graph, with a
  backward-compatible constructor.
- `outlook-provider`: moved off `Office365-REST-Python-Client` onto the shared Graph core
  (alias/subclass).
- `azure-extra-dependencies`: remove `Office365-REST-Python-Client` and `pyo365`, and `o365` once
  nothing imports it.

---

## Impact & Integration

| Affected Component | Impact Type | Notes |
|---|---|---|
| `notify/providers/office365/office365.py` | modifies (rewrite) | Graph backend; `input()`, `print()`, recursive retry and O365 imports removed |
| `notify/providers/office365/__init__.py` | modifies | docstring still says "Using O365 library" |
| `notify/providers/outlook/outlook.py` | modifies (rewrite to alias) | drop `office365.graph_client`, `msal` direct use and `/me` |
| new shared Graph mail core + token layer (under `notify/providers/`) | extends | credential adapter, token stores, message builder |
| `notify/providers/teams/_msgraph_patch.py` | depends on (maybe relocate) | needed by mail too; consider moving to a shared location |
| `notify/conf.py` | modifies | new `O365_*` settings (auth flow, sender, certificate, token store) |
| `pyproject.toml` (`azure`, `all` extras) | modifies | remove `Office365-REST-Python-Client`, `pyo365`, probably `o365`; keep `msal`, `msgraph-*`, `azure-identity` |
| `notify/server/wrapper.py` | depends on / policy | OBO assertions must not be persisted through queue kwargs |
| `tests/test_outlook.py`, `tests/test_outlook1.py` | modifies | they patch `outlook.acquire_token` / `outlook.client`, which will disappear |
| `examples/test_o365.py`, `examples/test_outlook.py` | modifies | update to the new auth flows |
| `docs/providers.rst` (`office365` at line ~220, `outlook` at line ~467) | modifies | fix the inaccurate feature list; document flows, send-as, OBO and tenant setup |
| `README.md` | modifies | provider usage |
| **Breaking?** | minor | constructor kept; the interactive token bootstrap and `.o365_token.txt` behaviour change; `outlook.acquire_token*` methods go away |

---

## Code Context

### User-Provided Code
_None provided. The decisions came from discovery answers (see Constraints & Requirements)._

### Verified Codebase References

#### Classes & Signatures
```python
# From notify/providers/base.py:31
class ProviderBase(ABC):
    provider: str = None                                   # line 37
    provider_type: ProviderType = ProviderType.NOTIFY      # line 38
    blocking: bool = True                                  # line 39
    sent: Optional[Union[Callable, Awaitable]] = None      # line 40
    def __init__(self, *args, **kwargs): ...               # line 42 — copies unknown kwargs onto self (lines 77-81)
    async def __aenter__(self) -> "ProviderBase": ...      # line 84 — calls connect()
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None: ...  # line 88 — calls close()
    async def connect(self, *args, **kwargs): ...          # line 96 (abstract)
    async def close(self): ...                             # line 100 (abstract)
    async def _prepare_(self, recipient: Actor = None, message: Union[str, Any] = None, ...): ...  # line 117
    async def _send_(self, to: Actor, message: Union[str, Any], subject: str = None, **kwargs) -> Any: ...  # line 209
    async def __sent__(self, recipient: Actor, message: str, result: Optional[Any], **kwargs): ...  # line 226 — forwards **kwargs to self.sent
    async def send(self, recipient: list[Actor] = None, message: Union[str, Any] = None, subject: str = None, **kwargs): ...  # line 263

# From notify/providers/mail.py:15
class ProviderEmail(ProviderBase, ABC):
    provider_type = ProviderType.EMAIL                     # line 22
    blocking: str = 'asyncio'                              # line 23
    timeout: int = 60                                      # line 24
    async def connect(self, *args, **kwargs): ...          # line 47 — aiosmtplib SMTP connect
    async def _render_(self, to: Actor = None, message: str = None, subject: str = None, **kwargs): ...  # line 104 — MIME
    def add_attachment(self, message, filename, mimetype="octect-stream"): ...  # line 158
    async def _send_(self, to: Actor, message: str, subject: str, **kwargs): ...  # line 181
    async def send(self, recipient: list[Actor] = None, message: Union[str, Any] = None, subject: str = None, **kwargs): ...
        # line 209 — calls self.connect() on EVERY send (line 224), fans out _send_ per recipient,
        # swallows per-recipient exceptions with a warning (lines 242-249)

# From notify/providers/office365/office365.py:34  (CURRENT — to be rewritten)
class Office365(ProviderEmail):
    provider = "office365"                                 # line 41
    blocking: str = 'asyncio'                              # line 42
    def __init__(self, *args, username: str = None, password: str = None, use_credentials: bool = True,
                 client_id: str = None, client_secret: str = None, tenant_id: str = None, **kwargs): ...  # line 44
    async def connect(self, **kwargs): ...   # line 88 — MSOffice365Protocol, scopes ["https://outlook.office.com/.default"] (line 95),
                                             # FileSystemTokenBackend('.o365_token.txt') (lines 97-101), print()+input() (lines 112-114),
                                             # recursive self.connect() after unlinking token (lines 147-151)
    async def close(self): ...               # line 153 — no-op
    async def _render_(self, to: Actor, message: str = None, subject: str = None, **kwargs): ...  # line 156
    async def _send_(self, to: Actor, message: str, subject: str, **kwargs): ...  # line 190 — message.send() is sync (blocking)

# From notify/providers/outlook/outlook.py:22  (CURRENT — to be rewritten)
class Outlook(ProviderEmail):
    provider = "outlook"                                   # line 29
    blocking: str = 'asyncio'                              # line 30
    def __init__(..same kwargs as Office365..): ...        # line 32; self.scopes = ["https://graph.microsoft.com/.default"] (line 61)
    def acquire_token(self): ...                           # line 79 — msal CCA acquire_token_for_client
    def acquire_token_by_username(self): ...               # line 91 — msal PCA ROPC
    async def add_attachment(self, filename): ...          # line 103 — aiofiles + base64
    async def connect(self, **kwargs): ...                 # line 117 — GraphClient(self.acquire_token*)
    async def close(self): ...                             # line 133
    async def _render_(self, to: Actor, message: str = None, subject: str = None, **kwargs): ...  # line 136 — self.client.me.send_mail(...) (line 153)
    async def _send_(self, to: Actor, message: str, subject: str, **kwargs): ...  # line 164 — message.execute_query() (sync)

# From notify/providers/teams/teams.py:60  (pattern to follow)
class Teams(ProviderIM):
    def get_graph_client(self, client: Any, scopes: Optional[list] = None):  # line 88
        return GraphServiceClient(credentials=client, scopes=scopes)          # line 91
    async def connect(self, *args, **kwargs): ...                             # line 93 — msal + ClientSecretCredential (line 120) / UsernamePasswordCredential (line 106)

# From notify/providers/teams/_msgraph_patch.py:31
def patch_graph_host_os_header() -> bool: ...   # idempotent; called at teams.py:57

# From notify/models.py
class Account(BaseModel):   # line 28 — provider, enabled, address: Union[str, list[str]], number, userid, attributes
class Actor(BaseModel):     # line 44 — userid: uuid.UUID, name: str, account: Optional[Account], accounts: Optional[list[Account]]
class Attachment(BaseModel):  # line 96 — name, content, content_type, type
class MailAttachment(Attachment):  # line 129 — subject, filename, content_disposition, attachment, size
class MailMessage(BlockMessage):   # line 137 — directory, content, attachments: list[MailAttachment]

# From notify/notify.py
PROVIDERS = {}                                            # line 10
class Notify:                                             # line 18
    def __new__(cls, provider: str, *args, **kwargs): ... # line 31 — LoadProvider(provider), cached in PROVIDERS

# From notify/server/wrapper.py:40
def __init__(self, provider: str, *args, **kwargs): ...   # same self.kwargs go to Notify(...) (lines 71, 83) and to send() (lines 75, 87)
```

#### Verified Imports
```python
# Confirmed to import in the project .venv (2026-09-15):
from msgraph import GraphServiceClient
    # __init__(self, credentials: Optional[Union[TokenCredential, AsyncTokenCredential]] = None,
    #          scopes: Optional[List[str]] = None, request_adapter: Optional[GraphRequestAdapter] = None)
from msgraph.generated.users.item.send_mail.send_mail_post_request_body import SendMailPostRequestBody
    # fields: message, save_to_sent_items (+ backing_store, additional_data)
from msgraph.generated.users.item.send_mail.send_mail_request_builder import SendMailRequestBuilder
    # async post(self, body: SendMailPostRequestBody, request_configuration=None) -> None
from msgraph.generated.models.message import Message
    # fields include: subject, body, from_, sender, to_recipients, cc_recipients, bcc_recipients,
    #                 reply_to, importance, attachments
from msgraph.generated.models.item_body import ItemBody        # used in teams.py:16
from msgraph.generated.models.body_type import BodyType        # used in teams.py:17
from msgraph.generated.models.recipient import Recipient
from msgraph.generated.models.email_address import EmailAddress
from msgraph.generated.models.importance import Importance
from msgraph.generated.models.file_attachment import FileAttachment
    # fields include: name, content_type, content_bytes, content_id, is_inline
from msgraph.generated.models.attachment_item import AttachmentItem
from msgraph.generated.models.attachment_type import AttachmentType
from msgraph.generated.users.item.messages.item.attachments.create_upload_session.create_upload_session_post_request_body import CreateUploadSessionPostRequestBody
from msgraph.generated.models.o_data_errors.o_data_error import ODataError
from msgraph_core.tasks.large_file_upload import LargeFileUploadTask
    # __init__(self, upload_session: Parsable, request_adapter: RequestAdapter, stream: BytesIO,
    #          parsable_factory=None, max_chunk_size: int = 5242880)
from azure.identity.aio import ClientSecretCredential, CertificateCredential, OnBehalfOfCredential
    # OnBehalfOfCredential(tenant_id, client_id, *, client_certificate=None, client_secret=None,
    #                      client_assertion_func=None, user_assertion: str, password=None, **kwargs)
from azure.identity import DeviceCodeCredential, UsernamePasswordCredential, TokenCachePersistenceOptions, AuthenticationRecord
import msal
    # msal.ConfidentialClientApplication.acquire_token_on_behalf_of(self, user_assertion, scopes, claims_challenge=None, **kwargs)
    # msal.PublicClientApplication.initiate_device_flow / acquire_token_by_device_flow — present
    # msal.ClientApplication.__init__ accepts token_cache=
    # msal.SerializableTokenCache — present
from notify.providers.mail import ProviderEmail           # notify/providers/mail.py:15
from notify.providers.base import ProviderBase, ProviderType  # notify/providers/base.py:23,31
from notify.exceptions import NotifyAuthError, ProviderError  # used at office365.py:20, mail.py:9
from notify.models import Actor                            # notify/models.py:44
from notify.providers.office365 import Office365          # notify/providers/office365/__init__.py:7
from notify.providers.outlook import Outlook              # notify/providers/outlook/__init__.py:7
```

Installed versions (verified): `msgraph-sdk 1.22.0`, `msgraph-core 1.3.2`, `azure-identity 1.25.3`,
`azure-core 1.41.0`, `msal 1.32.0`, `o365 2.0.37`, `office365-rest-python-client 2.5.13`
(`pyo365` is listed in extras but **not installed**).

#### Key Attributes & Constants
- `notify.conf.O365_CLIENT_ID` / `O365_CLIENT_SECRET` / `O365_TENANT_ID` / `O365_USER` /
  `O365_PASSWORD` → `str | None` (notify/conf.py:68-72)
- `Office365.provider` → `"office365"` (office365.py:41); `Outlook.provider` → `"outlook"` (outlook.py:29)
- `Outlook.scopes` → `["https://graph.microsoft.com/.default"]` (outlook.py:61)
- `pyproject.toml` `azure` extra pins `o365>=2.0.37,<2.1` with the comment "2.1 removed
  MSOffice365Protocol (used by the office365 provider)".
- Graph upload chunk default: `LargeFileUploadTask.max_chunk_size = 5242880` (5 MiB).

### Does NOT Exist (Anti-Hallucination)
- ~~`azure.identity.aio.DeviceCodeCredential`~~ — no async device-code credential; only the sync `azure.identity.DeviceCodeCredential`.
- ~~`azure.identity.aio.UsernamePasswordCredential`~~ — sync only, and deprecated (emits "UsernamePasswordCredential is deprecated, as it doesn't support multifactor authentication (MFA)").
- ~~Redis persistence in `azure.identity.TokenCachePersistenceOptions`~~ — it only takes `allow_unencrypted_storage` and `name` (msal-extensions file/keyring), not a custom or Redis backend.
- ~~An `on_behalf_of` auth flow in `O365.Connection`~~ — O365 2.0.37 supports only `authorization`, `public`, `credentials`, `certificate`, `password`.
- ~~Graph usage in the current `office365` provider~~ — it uses `MSOffice365Protocol` (Outlook REST), despite `docs/providers.rst` saying otherwise.
- ~~A shared Graph/MSAL helper module in `notify/`~~ — Graph wiring exists only inside `notify/providers/teams/`.
- ~~A token-store abstraction in `notify/`~~ — none exists; `office365` hardcodes `FileSystemTokenBackend('.o365_token.txt')`.
- ~~`cc`, `bcc`, `reply_to`, `from_address`, `user_assertion` kwargs on any email provider~~ — no email provider handles them today (only `attachments` in `mail.py`/`smtp.py`).
- ~~An offline test for `office365`~~ — only `tests/test_outlook.py` and `tests/test_outlook1.py` exist (for `outlook`); `examples/test_o365.py` is a manual script.
- ~~`pyo365` installed~~ — listed in the `azure` extra but not present in the venv.

---

## Parallelism Assessment

- **Internal parallelism**: moderate. Once the token layer's interface is agreed, three parts can
  move independently: (1) the token store backends (memory/file/Redis) and the MSAL credential
  adapter, (2) the Graph mail core (message builder, attachments/upload sessions, CID images), and
  (3) the device-code bootstrap helper plus docs/examples. The `office365` rewrite, the `outlook`
  alias, the `pyproject.toml` cleanup and the integration tests depend on (1) and (2).
- **Cross-feature independence**: no spec in progress touches `notify/providers/office365/` or
  `outlook/`. Possible overlap: `notify/providers/mail.py` / `_mime_utils.py` (NAV-8390
  email-utf8 — if the rewrite changes `ProviderEmail` rather than just overriding in the provider),
  `notify/templates.py` (templateparser-refactor, jinja-string-notify — this feature only calls
  `render_async`), `pyproject.toml` extras (any dependency change), and
  `notify/providers/teams/_msgraph_patch.py` if it moves to a shared location (the Teams provider
  imports it).
- **Recommended isolation**: `per-spec`
- **Rationale**: the pieces share a small internal contract (credential adapter ↔ Graph client ↔
  provider) that is still in flux. Keeping all tasks in one worktree run in order avoids interface
  drift and merge churn in `conf.py` and `pyproject.toml`. The work is too small for the overhead
  of `mixed` worktrees.

---

## Open Questions

- [x] Flow type and base branch? — *Owner: Jesus Lara*: `type: feature`, `base_branch: dev`.
- [x] What does "on behalf of" mean? — *Owner: Jesus Lara*: both send-as / from another mailbox **and** the OAuth2 OBO token flow.
- [x] Which provider gets Graph support? — *Owner: Jesus Lara*: rewrite `office365` on Graph (keep the name).
- [x] Which auth flows must work? — *Owner: Jesus Lara*: client credentials, OBO user assertion, delegated with cached token, username/password (ROPC).
- [x] How does the OBO user token reach the provider? — *Owner: Jesus Lara*: per-send kwarg (`user_assertion=`), per-user token cache, one instance for many users.
- [x] Token storage? — *Owner: Jesus Lara*: pluggable, in-memory default, file/Redis backends.
- [x] Backward compatibility? — *Owner: Jesus Lara*: keep constructor kwargs, add `auth_flow`, warn on legacy (ROPC); remove the `input()` flow.
- [x] Launch mail features? — *Owner: Jesus Lara*: attachments incl. >3 MB, CC/BCC/Reply-To, save-to-sent-items control, inline CID images.
- [x] What happens to `outlook` / `Office365-REST-Python-Client`? — *Owner: Jesus Lara*: the package is broken and must be replaced completely by ms-graph (`msgraph-sdk`); `outlook` moves onto the same Graph core.
- [x] Delegated bootstrap method? — *Owner: Jesus Lara*: device code.
- [x] Send-as mailbox source? — *Owner: Jesus Lara*: instance default (`sender=`) overridable per send (`from_address=`), for app-only and delegated/OBO.
- [x] Live test tenant available? — *Owner: Jesus Lara*: yes, an existing Entra ID tenant is available for `@pytest.mark.integration` tests.
- [ ] With several recipients, send one Graph message addressed to all of them, or keep today's one message per recipient (`ProviderEmail.send()` fan-out)? This changes how CC/BCC behave. — *Owner: Jesus Lara*
- [ ] Should `o365` be dropped from the `azure`/`all` extras entirely once `office365` stops importing it (a breaking dependency change for anyone using `O365` directly through this extra)? — *Owner: Jesus Lara*
- [ ] Should `outlook` stay a silent alias, or also log a `DeprecationWarning` pointing to `office365`? — *Owner: Jesus Lara*
- [ ] Policy for OBO jobs through the notify server (Redis queue): reject `user_assertion` in queued jobs, encrypt it, or only allow direct sends? — *Owner: Jesus Lara*
- [ ] Redis token store security: require encryption at rest (key from navconfig) or allow plaintext behind an explicit opt-in? — *Owner: Jesus Lara*
- [ ] Where does the device-code bootstrap live: a `python -m notify.providers.office365.login` entry point, a Makefile target, or a documented API only? — *Owner: Jesus Lara*
- [ ] Certificate-based client credentials (`CertificateCredential` / MSAL cert) at launch, or client secret only? — *Owner: Jesus Lara*
- [ ] How should Graph failures surface, given `ProviderEmail.send()` swallows per-recipient exceptions: a result object per recipient, or a `raise_on_error` option? — *Owner: Jesus Lara*
- [ ] Move `_msgraph_patch.py` from `providers/teams/` to a shared module (e.g. `notify/providers/_msgraph.py`) now that two providers need it? — *Owner: Jesus Lara*
