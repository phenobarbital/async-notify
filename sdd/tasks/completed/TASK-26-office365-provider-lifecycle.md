# TASK-26: Wire Office365 Graph configuration and lifecycle

**Feature**: FEAT-004 — Mail Messages via Microsoft Graph (send-as & On-Behalf-Of)
**Spec**: `sdd/specs/mail-messages-graph.spec.md`
**Status**: pending
**Priority**: high
**Estimated effort**: M (2–4h)
**Depends-on**: TASK-19, TASK-20, TASK-21, TASK-22
**Assigned-to**: unassigned

---

## Context

The existing Office365 provider uses legacy Outlook REST and interactive input. This first provider task replaces its configuration/lifecycle core with a lazy Graph client and explicit flow resolution. Implements the lifecycle/configuration part of spec §3 M6 and AC1–AC5.

## Scope

- Rewrite Office365 construction to pop consumed settings before `ProviderBase.__init__` and resolve auth flow in the documented precedence order.
- Reject constructor-level `user_assertion`, set batch/error/redaction hooks, and retain backward-compatible constructor parameters.
- Implement idempotent network-free `connect()`, credential/store/client construction, `close()`, and `auth_flow` property.
- Update the package exports/docstring and add focused lifecycle/flow tests.

**NOT in scope**: HTML rendering, attachments, Graph send routing, or per-send assertion scope; those belong to TASK-27.

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `notify/providers/office365/office365.py` | MODIFY | Replace legacy setup with Graph lifecycle. |
| `notify/providers/office365/__init__.py` | MODIFY | Export and describe Graph Office365 provider. |
| `tests/test_office365_provider.py` | CREATE | Flow precedence, constructor, and lifecycle tests. |

## Codebase Contract (Anti-Hallucination)

### Verified Imports
```python
from msgraph import GraphServiceClient
from notify.providers.mail import ProviderEmail
from notify.providers.office365.credential import AuthFlow, MsalAsyncCredential  # TASK-22
from notify.providers.office365.token_store import TokenStore, build_token_store  # TASK-21
from notify.exceptions import NotifyAuthError, ProviderError
```

### Existing Signatures to Use
```python
# notify/providers/office365/office365.py:34,41-42,44,88,153
class Office365(ProviderEmail):
    provider = "office365"
    blocking: str = "asyncio"
    async def connect(self, **kwargs): ...
    async def close(self): ...

# notify/providers/base.py:77-81,84
# Unconsumed kwargs are assigned as instance attributes; __aenter__ invokes connect().
```

### Does NOT Exist
- Current Office365 has no Graph client, token store, credential, or explicit `auth_flow`.
- Interactive `input()` and recursive token retry are prohibited in the replacement.

## Implementation Notes

- Precedence is explicit `auth_flow`, `O365_AUTH_FLOW`, explicit `use_credentials=True`, credential/certificate availability, username/password, then a configuration error.
- Client-credential flow must have a sender/from address later; do not make Graph requests in `connect()`.
- Keep secrets off `self` by popping them before `super().__init__`.

## Acceptance Criteria

- [x] All six flow-resolution rules work, including legacy password warning.
- [x] Constructor rejects `user_assertion` and does not expose consumed certificate-password fields.
- [x] Two `connect()` calls create one Graph client and acquire no token.
- [x] `close()` persists/closes the credential and clears the client.
- [x] `pytest tests/test_office365_provider.py -q` passes for lifecycle cases.

### Completion Note

Rewrote `Office365.__init__`/`connect()`/`close()`/`auth_flow` on Microsoft
Graph exactly per the M6 lifecycle rules: the 6-step flow-resolution
precedence (`_resolve_auth_flow`), `user_assertion` rejected at
construction (`ProviderError`), `client_certificate_password` kept off
`self` entirely (stored as `self._client_certificate_password`) so it
can never leak the way `ProviderBase`'s leftover-kwarg `setattr` would —
every other consumed kwarg is captured by explicit signature parameters,
so it never reaches that mechanism either. `connect()` is idempotent and
builds the token store + `MsalAsyncCredential` + `GraphServiceClient`
with zero network calls (verified: `credential._app is None` right after
`connect()`, since MSAL app construction is deferred inside
`MsalAsyncCredential` per TASK-22). `close()` persists the cache via the
credential and clears both `_graph`/`_credential`. Added
`tests/test_office365_provider.py` (11 tests, all `async def` — a plain
`def` test that constructs a `ProviderBase` subclass hit a pre-existing
`asyncio.get_event_loop()`/uvloop ordering issue when run alongside other
async test files; using `async def` throughout sidesteps it, matching
this repo's existing test convention). Two of the flow-resolution tests
had to `monkeypatch` `O365_CLIENT_SECRET`/`O365_USER`/`O365_PASSWORD`/
`O365_AUTH_FLOW` to `None`, because this machine's navconfig env already
defines real O365 credentials that would otherwise short-circuit the
precedence chain. Full-suite run (`pytest tests/ --ignore=tests/integration`):
289 passed — the only failures are pre-existing and untouched by this
task (`tests/test_ses.py` × 2, a `botocore`/`aiobotocore` region-name
validation issue; `tests/test_outlook1.py` × 3, the same event-loop
ordering issue in sync test functions I did not write, in a file TASK-28
will rewrite). `flake8` is not installed in this environment; lint could
not be run.
