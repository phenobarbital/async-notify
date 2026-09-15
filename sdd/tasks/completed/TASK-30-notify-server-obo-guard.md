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

- [x] Both payload shapes raise `MessageError` mentioning the key only.
- [x] Redis `xadd` and serialization are not invoked after rejection.
- [x] Wrapper construction cannot retain the assertion.
- [x] `pytest tests/test_notify_server_guard.py -q` passes.

### Completion Note

Added `QUEUE_FORBIDDEN_KWARGS = frozenset({"user_assertion"})` and
`reject_queued_secrets(message)` to `notify/server/wrapper.py`: it checks
the top-level `message` keys and, when present, a nested `kwargs` dict,
and raises `MessageError` naming only the key. Called as the literal
first statement of `NotifyWrapper.__init__` (`reject_queued_secrets({**kwargs})`)
and of `NotifyClient.publish`/`stream`/`send` (`reject_queued_secrets(message)`),
before `json.dumps`, `cloudpickle.dumps`, or any Redis/TCP call —
`server.py:507`'s `NotifyWrapper(**msg)` call site is covered automatically
since the guard lives in the constructor itself, needing no separate edit
there. Added `tests/test_notify_server_guard.py` (11 tests: constant
value, top-level/nested rejection with value-never-in-message-check,
clean-message pass-through, wrapper-construction rejection, client
publish/stream/send rejection-before-any-redis-or-tcp-call via mocks
asserted `not_called()`, the `use_wrapper=True` stream shape, and a clean
message actually reaching `redis.publish`) — all pass. Noted but
deliberately NOT fixed (out of scope, pre-existing, unrelated to the
guard): `NotifyClient.publish`/`stream` call `self.connect_redis()`,
which does not exist on the class (only `connect()` does) — this bug
only surfaces on the "no redis yet" branch of the *allowed*-message path,
which my tests avoid by pre-seeding `client.redis` with a mock (as the
guard-rejection tests do not depend on it either way, since the guard
raises before that branch is ever reached). `flake8` is not installed in
this environment; lint could not be run.
