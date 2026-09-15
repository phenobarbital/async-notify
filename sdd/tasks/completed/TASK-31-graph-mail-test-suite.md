# TASK-31: Add the Graph mail offline and integration test suite

**Feature**: FEAT-004 — Mail Messages via Microsoft Graph (send-as & On-Behalf-Of)
**Spec**: `sdd/specs/mail-messages-graph.spec.md`
**Status**: pending
**Priority**: high
**Estimated effort**: L (4–8h)
**Depends-on**: TASK-19, TASK-20, TASK-21, TASK-22, TASK-23, TASK-24, TASK-25, TASK-26, TASK-27, TASK-28, TASK-29, TASK-30
**Assigned-to**: unassigned

---

## Context

The feature changes provider transport, authentication, callbacks, queuing, and attachment behavior. This final verification task consolidates offline mocks, rewrites REST-era Outlook tests, and creates credential-gated live coverage. Implements spec §3 M11, §4, and AC1–AC17.

## Scope

- Complete or consolidate offline tests for all M1–M10 cases enumerated in spec §4.
- Rewrite legacy Outlook tests to use plain fixtures rather than `BaseTestCase`’s real-connect behavior.
- Create `tests/integration/test_office365_live.py` with `@pytest.mark.integration` scenarios that skip when required navconfig values are absent.
- Mock Graph SDK and MSAL for unit tests; ensure no unit test makes a network call.
- Execute targeted tests and the appropriate non-live suite after the implementation tasks land.

**NOT in scope**: making live tenant credentials mandatory in CI, provisioning Azure resources, or changing public behavior beyond test-driven defect fixes within preceding task scopes.

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `tests/test_office365_graph.py` | MODIFY | Complete mocked builder/sender coverage. |
| `tests/test_office365_token_store.py` | MODIFY | Complete store security coverage. |
| `tests/test_office365_credential.py` | MODIFY | Complete MSAL flow/isolation coverage. |
| `tests/test_office365_provider.py` | MODIFY | Complete provider behavior coverage. |
| `tests/test_office365_login.py` | MODIFY | Complete CLI coverage. |
| `tests/test_mail_hooks.py` | MODIFY | Complete hook compatibility coverage. |
| `tests/test_notify_server_guard.py` | MODIFY | Complete pre-serialization guard coverage. |
| `tests/test_outlook.py` | MODIFY | Graph alias regression coverage. |
| `tests/test_outlook1.py` | MODIFY | Graph alias regression coverage. |
| `tests/integration/test_office365_live.py` | CREATE | Gated tenant integration coverage. |

## Codebase Contract (Anti-Hallucination)

### Verified Imports
```python
from unittest.mock import AsyncMock, MagicMock
import pytest
from notify.models import Actor
from notify.notify import Notify
```

### Existing Signatures to Use
```python
# notify/tests/base.py:7-35
class BaseTestCase:
    # autouse setup invokes connect()/close() and expects legacy client attributes

# pytest.ini defines asyncio auto mode and the integration marker (spec §4).
```

### Does NOT Exist
- `tests/integration/` does not exist yet.
- Existing Office365 tests do not provide an offline Graph test suite.
- Unit tests must not rely on a real Entra tenant, Redis server, or Graph endpoint.

## Implementation Notes

- Keep each module test focused; fixtures should expose an `AsyncMock` Graph builder graph and mocked MSAL applications.
- Test the pre-issued assertion integration path only when its navconfig setting exists; do not manufacture credentials or use ROPC for it.
- Test behavior, not private SDK implementation details, and include the no-legacy-import regression.

## Acceptance Criteria

- [x] Every unit test named in spec §4 has offline coverage.
- [x] Live tests cover app-only send-as, large upload, CC/BCC/CID, OBO, delegated silent cache, and denied send-as, each skipped without configuration.
- [x] Existing Outlook tests no longer hit a real `connect()` path.
- [x] The targeted unit suite passes without network access.
- [x] Integration tests are marker-gated and skipped cleanly without tenant settings.

### Completion Note

Audited every unit test named in spec §4 against the offline suites
already built incrementally by TASK-19–TASK-30: all are covered (the
6-rule flow-resolution precedence is covered as 6 discrete tests rather
than one parametrised test — same semantic coverage). Filled the one
real gap: `test_no_removed_libraries_imported` (M6/M7/M9), added to
`tests/test_office365_provider.py`, checking `sys.modules` after
importing both providers.

Fixed a stale Codebase Contract claim along the way (per the "update the
contract, then proceed" rule): `pytest.ini` did NOT actually define the
`integration`/`live`/`real_llm` markers the spec's Codebase Contract and
this task's own contract both assert already exist — verified empirically
(no `markers =` section, and `pyproject.toml`'s `[tool.pytest.ini_options]`
with `--strict-markers` is dead config, since `pytest.ini`'s presence
makes pytest ignore `pyproject.toml` entirely, confirmed by pytest's own
`configfile: pytest.ini (WARNING: ignoring pytest config in
pyproject.toml!)` banner). Registered all three markers in `pytest.ini`
so the new integration file collects cleanly with no warning.

Created `tests/integration/test_office365_live.py`: 6
`@pytest.mark.integration` scenarios (app-only send-as, 5 MB attachment
via upload session, CC/BCC + inline CID image, on_behalf_of with a
pre-issued `O365_TEST_USER_ASSERTION` per spec §8, delegated silent-after-
`login.py`-seed, and send-as-denied → `NotifyAuthError`), each individually
`skipif`-gated on the navconfig settings it needs (none are manufactured;
the deprecated `password`/ROPC flow is never used to obtain one) — all 6
skip cleanly (verified both via `pytest -m integration
tests/integration/test_office365_live.py -v` and inside a full
`pytest tests/` run).

Rewrote `tests/test_outlook.py` off `notify.tests.base.BaseTestCase` onto
plain async fixtures (resolves spec §8's open question, owned by "the
implementer (M11)" — this task): `BaseTestCase`'s autouse fixture assumed
a legacy REST lifecycle and an `authenticate` attribute that no longer
exist; `connect()` itself is still perfectly safe to call for real
(network-free per TASK-26), so the new tests call it directly through
`Notify("outlook", ...)` rather than mocking it away.

Full-suite run (`pytest tests/`, no `--ignore`): **328 passed, 6 skipped,
2 xfailed** — the only failures are the same pre-existing, untouched
`tests/test_ses.py` × 2 (`botocore`/`aiobotocore` region-name validation).
AC18's exact command
(`pytest tests/test_office365_graph.py tests/test_office365_token_store.py
tests/test_office365_credential.py tests/test_mail_hooks.py
tests/test_notify_server_guard.py tests/test_outlook.py tests/test_outlook1.py -v`):
**75 passed**. No unit test imports `aiohttp`/`requests`/`httpx` client
classes or touches a real Graph/MSAL/Redis endpoint (spot-checked via
grep across every FEAT-004 test file). `flake8` is not installed in this
environment; lint could not be run.
