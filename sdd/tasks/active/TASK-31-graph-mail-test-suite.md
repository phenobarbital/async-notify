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

- [ ] Every unit test named in spec §4 has offline coverage.
- [ ] Live tests cover app-only send-as, large upload, CC/BCC/CID, OBO, delegated silent cache, and denied send-as, each skipped without configuration.
- [ ] Existing Outlook tests no longer hit a real `connect()` path.
- [ ] The targeted unit suite passes without network access.
- [ ] Integration tests are marker-gated and skipped cleanly without tenant settings.
