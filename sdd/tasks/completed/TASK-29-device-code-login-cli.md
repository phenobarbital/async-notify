# TASK-29: Add the Office365 device-code login command

**Feature**: FEAT-004 — Mail Messages via Microsoft Graph (send-as & On-Behalf-Of)
**Spec**: `sdd/specs/mail-messages-graph.spec.md`
**Status**: pending
**Priority**: medium
**Estimated effort**: M (2–4h)
**Depends-on**: TASK-20, TASK-21, TASK-22
**Assigned-to**: unassigned

---

## Context

Delegated mail needs a headless one-time sign-in that seeds a persistent MSAL cache, replacing interactive provider prompts. Implements spec §3 M8, AC2, and AC16.

## Scope

- Create `device_code_login()` using delegated `MsalAsyncCredential` and a supplied `TokenStore`.
- Implement `main()` with required username and optional tenant/client/token-store overrides.
- Print device instructions and errors through `sys.stderr.write`; return the documented 0/1/2 codes.
- Refuse the memory token store and test success/error paths with mocks.

**NOT in scope**: web redirects, a provider-side `input()` flow, or handling assertions/OBO.

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `notify/providers/office365/login.py` | CREATE | Headless device-code entry point. |
| `tests/test_office365_login.py` | CREATE | CLI argument and mocked device-flow tests. |

## Codebase Contract (Anti-Hallucination)

### Verified Imports
```python
from notify.providers.office365.credential import AuthFlow, MsalAsyncCredential  # TASK-22
from notify.providers.office365.token_store import TokenStore, build_token_store  # TASK-21
from notify.exceptions import NotifyAuthError
```

### Existing Signatures to Use
```python
# credential.py interface created by TASK-22
async def initiate_device_flow(self, scopes=None) -> dict: ...
async def complete_device_flow(self, flow: dict) -> None: ...
```

### Does NOT Exist
- An async Azure Identity device-code credential is not available for this design.
- A memory-store bootstrap cannot persist a delegated cache and must be rejected.

## Implementation Notes

- Run async work from the synchronous CLI using the project’s standard event-loop-safe approach.
- Avoid printing secrets, cache contents, or configuration values.

## Acceptance Criteria

- [x] `--token-store memory` exits 2 and explains why it is unsafe for bootstrap.
- [x] Successful mocked device flow persists the cache and exits 0.
- [x] `NotifyAuthError`, including timeouts, exits 1 through stderr.
- [x] `pytest tests/test_office365_login.py -q` passes.

### Completion Note

Added `notify/providers/office365/login.py` with `device_code_login()`
(builds a `DELEGATED` `MsalAsyncCredential`, runs `initiate_device_flow`
→ `complete_device_flow`, always closes the credential in a `finally`)
and `main()` (argparse: `--username` required, `--tenant-id`/`--client-id`
default to `O365_TENANT_ID`/`O365_CLIENT_ID`, `--token-store` accepts
`memory`/`file`/`redis` but explicitly rejects `memory` with a
explanatory stderr message before anything else runs — accepting it as
an argparse choice, rather than omitting it, is what let me give the
specific "would lose the token" message instead of argparse's generic
"invalid choice" text). Exit codes: `2` for `--token-store memory` or a
missing tenant/client id, `1` for any `NotifyAuthError` from
`device_code_login` (its message reaches stderr, unmodified — MSAL error
text never contains secrets per TASK-22), `0` on success. All output is
`sys.stderr.write`, never `print`. Added
`tests/test_office365_login.py` (8 tests: memory-store refusal, missing
tenant/client id, argparse's own missing-`--username` exit 2, a fully
mocked successful CLI run, a mocked `NotifyAuthError` CLI run, and two
`device_code_login()`-level tests against a fake credential covering the
full flow and error propagation) — all pass. `flake8` is not installed
in this environment; lint could not be run.
