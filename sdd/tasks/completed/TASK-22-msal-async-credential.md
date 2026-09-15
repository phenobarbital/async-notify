# TASK-22: Implement the MSAL-backed asynchronous credential

**Feature**: FEAT-004 — Mail Messages via Microsoft Graph (send-as & On-Behalf-Of)
**Spec**: `sdd/specs/mail-messages-graph.spec.md`
**Status**: pending
**Priority**: high
**Estimated effort**: L (4–8h)
**Depends-on**: TASK-19, TASK-21
**Assigned-to**: unassigned

---

## Context

All Graph flows use one `AsyncTokenCredential` implementation backed by MSAL and the token-store contract. Context-isolated OBO assertions and executor-only MSAL calls are security-critical. Implements spec §3 M3 and AC2, AC3, and AC5.

## Scope

- Create `AuthFlow`, scopes, and `MsalAsyncCredential` using `SerializableTokenCache` and `TokenStore`.
- Support client-secret/certificate credentials, OBO, delegated cache lookup/device flow, and deprecated password flow.
- Scope OBO assertions with `ContextVar`; keep all MSAL work in an executor and all secrets out of logs/errors.
- Persist only changed cache state under an async lock and implement lifecycle methods.
- Add the offline credential tests listed in spec §4.

**NOT in scope**: Graph mail requests, provider flow-precedence resolution, config declarations, or the command-line parser.

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `notify/providers/office365/credential.py` | CREATE | MSAL `AsyncTokenCredential` implementation. |
| `tests/test_office365_credential.py` | CREATE | Mocked flow, isolation, and secret-redaction tests. |

## Codebase Contract (Anti-Hallucination)

### Verified Imports
```python
from azure.core.credentials import AccessToken
from azure.core.credentials_async import AsyncTokenCredential
from notify.providers._msgraph import GRAPH_DEFAULT_SCOPE  # created by TASK-19
from notify.providers.office365.token_store import TokenStore  # created by TASK-21
```

### Existing Signatures to Use
```python
# azure.core.credentials_async.AsyncTokenCredential
async def get_token(self, *scopes, claims=None, tenant_id=None, enable_cae=False, **kwargs): ...

# MSAL contracts verified in spec §3 M3
ConfidentialClientApplication.acquire_token_on_behalf_of(user_assertion, scopes, claims_challenge=None, **kwargs)
SerializableTokenCache.has_state_changed
```

### Does NOT Exist
- `azure.identity.aio.DeviceCodeCredential` and `azure.identity.aio.UsernamePasswordCredential` do not provide this async flow.
- A token assertion must never be retained on the provider instance.

## Implementation Notes

- Use cache key `tenant_id:client_id:flow` and lazy cache loading.
- Convert MSAL error dictionaries into `NotifyAuthError` without assertions, secrets, certificate passwords, or tokens.
- Delegated account matching is case-insensitive by username; missing account points users to the module login command.

## Acceptance Criteria

- [x] Secret and certificate client credentials produce `AccessToken` via mocked MSAL.
- [x] Concurrent OBO contexts cannot mix assertions or tokens.
- [x] Delegated cache misses and password deprecation have the specified behavior.
- [x] Cache writes occur only after state changes.
- [x] `pytest tests/test_office365_credential.py -q` passes offline.

### Completion Note

Implemented `AuthFlow`, `scopes_for()`, and `MsalAsyncCredential` exactly per
the interface skeleton. One design addition beyond the skeleton, required
by MSAL's real behavior and consistent with spec §3 M6 ("`connect()` ...
makes no network call"): constructing `msal.ConfidentialClientApplication`/
`PublicClientApplication` triggers MSAL's OIDC *tenant discovery* HTTP call
unconditionally inside `Authority.__init__` (verified empirically — it is
not gated by `validate_authority`/`instance_discovery`, which only control
*instance* discovery). Building the MSAL app eagerly in `__init__` would
therefore make `Office365.connect()` hit the network. Fixed by deferring
app construction to a lazy `_ensure_app()` (executor-run, lock-guarded),
invoked from `get_token()` / `initiate_device_flow()` — mirroring the
already-lazy cache load. `__init__` still validates all required inputs
per flow synchronously and raises `NotifyAuthError` with no network I/O.
Added `tests/test_office365_credential.py` (10 tests covering secret/cert
client-credentials, OBO missing-assertion, OBO context isolation via
`asyncio.gather`, delegated cache-miss login hint, password
`DeprecationWarning`, cache-persist-only-on-change, and secret/assertion
never leaking into exception text) — all pass. `flake8` is not installed
in this environment; lint could not be run.
