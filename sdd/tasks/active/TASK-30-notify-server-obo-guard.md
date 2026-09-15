# TASK-30: Reject OBO assertions from queued notification payloads

**Feature**: FEAT-004 — Mail Messages via Microsoft Graph (send-as & On-Behalf-Of)
**Spec**: `sdd/specs/mail-messages-graph.spec.md`
**Status**: pending
**Priority**: high
**Estimated effort**: S (< 2h)
**Depends-on**: none
**Assigned-to**: unassigned

---

## Context

An OBO assertion is a user token and must never enter Redis, cloudpickle, or TCP queues. The rejection boundary must run before serialization on both client and worker paths. Implements spec §3 M10 and AC14.

## Scope

- Add `QUEUE_FORBIDDEN_KWARGS` and `reject_queued_secrets()` to the wrapper module.
- Call it as the first statement in wrapper construction and client `publish`, `stream`, and `send`.
- Check top-level payload keys and nested `kwargs`; error names the key but never its value.
- Add offline tests proving Redis/cloudpickle/TCP serialization is never reached.

**NOT in scope**: encrypting assertions for queues, arbitrary secret detection, or changing unrelated server serialization.

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `notify/server/wrapper.py` | MODIFY | Guard definition and wrapper entry point. |
| `notify/server/client.py` | MODIFY | Pre-serialization guard calls. |
| `tests/test_notify_server_guard.py` | CREATE | Direct and client-boundary tests. |

## Codebase Contract (Anti-Hallucination)

### Verified Imports
```python
from notify.exceptions import MessageError
from notify.server.wrapper import NotifyWrapper
```

### Existing Signatures to Use
```python
# notify/server/wrapper.py:40
def __init__(self, provider: str, *args, **kwargs): ...

# notify/server/client.py:99,108,130
async def publish(self, message: dict, channel: str): ...
async def stream(self, message: dict, stream: str, use_wrapper: bool = False): ...
async def send(self, message: dict): ...
```

### Does NOT Exist
- Queue payloads have no approved encrypted OBO-token representation.
- This guard must not log a forbidden value.

## Implementation Notes

- Reject if `user_assertion` appears either as a top-level message key or in nested `kwargs`.
- Call the shared guard before `json.dumps`, `cloudpickle.dumps`, Redis calls, and TCP connection attempts.

## Acceptance Criteria

- [ ] Both payload shapes raise `MessageError` mentioning the key only.
- [ ] Redis `xadd` and serialization are not invoked after rejection.
- [ ] Wrapper construction cannot retain the assertion.
- [ ] `pytest tests/test_notify_server_guard.py -q` passes.
