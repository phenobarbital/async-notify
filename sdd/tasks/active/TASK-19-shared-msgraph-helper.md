# TASK-19: Create the shared Microsoft Graph telemetry helper

**Feature**: FEAT-004 — Mail Messages via Microsoft Graph (send-as & On-Behalf-Of)
**Spec**: `sdd/specs/mail-messages-graph.spec.md`
**Status**: pending
**Priority**: high
**Estimated effort**: S (< 2h)
**Depends-on**: none
**Assigned-to**: unassigned

---

## Context

Microsoft Graph providers need one idempotent patch for the SDK's invalid `HostOs` telemetry header. This moves the existing Teams implementation into a shared provider module while keeping the old Teams import path valid. Implements spec §3 M1 and AC15.

## Scope

- Create the shared helper with `GRAPH_DEFAULT_SCOPE` and the existing patch behavior.
- Replace the Teams private helper with a compatibility re-export.
- Update Teams to import from the shared module.
- Add an offline identity/idempotence regression test.

**NOT in scope**: changing Teams authentication, Graph request behavior, or any Office365 provider implementation.

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `notify/providers/_msgraph.py` | CREATE | Shared Graph constants and HostOs patch. |
| `notify/providers/teams/_msgraph_patch.py` | MODIFY | Compatibility re-export shim. |
| `notify/providers/teams/teams.py` | MODIFY | Import the shared helper. |
| `tests/test_msgraph_helper.py` | CREATE | Offline patch and shim tests. |

## Codebase Contract (Anti-Hallucination)

### Verified Imports
```python
from msgraph_core.middleware.telemetry import GraphTelemetryHandler  # teams/_msgraph_patch.py:47
from notify.providers._msgraph import patch_graph_host_os_header    # new shared import
```

### Existing Signatures to Use
```python
# notify/providers/teams/_msgraph_patch.py:28-60
_PATCHED: bool = False
def patch_graph_host_os_header() -> bool: ...

# notify/providers/teams/teams.py:12,57
from ._msgraph_patch import patch_graph_host_os_header
patch_graph_host_os_header()
```

### Does NOT Exist
- `notify/providers/_msgraph.py` does not exist yet.
- A second Teams Graph client or a provider registration change is not needed.

## Implementation Notes

- Move the current function behavior verbatim: it must return `False` when `msgraph-core` is absent or incompatible, and remain idempotent.
- Keep `notify.providers.teams._msgraph_patch.patch_graph_host_os_header` identical to the shared function for backward compatibility.

## Acceptance Criteria

- [ ] `GRAPH_DEFAULT_SCOPE` is `https://graph.microsoft.com/.default`.
- [ ] Existing and shared import paths resolve to the same callable.
- [ ] The patch is idempotent and retains the existing missing-dependency behavior.
- [ ] `pytest tests/test_msgraph_helper.py -q` passes.
