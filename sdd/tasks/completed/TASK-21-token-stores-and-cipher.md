# TASK-21: Implement encrypted Office365 token stores

**Feature**: FEAT-004 — Mail Messages via Microsoft Graph (send-as & On-Behalf-Of)
**Spec**: `sdd/specs/mail-messages-graph.spec.md`
**Status**: pending
**Priority**: high
**Estimated effort**: M (2–4h)
**Depends-on**: TASK-20
**Assigned-to**: unassigned

---

## Context

MSAL needs asynchronous persistence for serialized caches, with safe defaults and no token leakage. This task creates memory, encrypted file, and Redis-backed stores. Implements spec §3 M2 and AC5.

## Scope

- Create `TokenCipher`, abstract `TokenStore`, and memory, file, and Redis implementations.
- Enforce encryption for persistent stores unless `allow_unencrypted=True` is explicit.
- Implement 0600 file writes, corrupt-value deletion, Redis fallback to in-process memory, optional TTL, and `build_token_store`.
- Add offline tests for every behavior in spec §4 M2.

**NOT in scope**: MSAL token acquisition, device-code login, or Office365 provider construction.

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `notify/providers/office365/token_store.py` | CREATE | Token cipher, stores, and factory. |
| `tests/test_office365_token_store.py` | CREATE | Offline store and encryption tests. |

## Codebase Contract (Anti-Hallucination)

### Verified Imports
```python
from redis import asyncio as aioredis                 # notify/server/client.py:6
from notify.exceptions import NotifyAuthError         # spec: exceptions.pyx:45
from notify.conf import NOTIFY_REDIS                   # notify/conf.py:17
```

### Existing Signatures to Use
```python
# notify/server/client.py:81-94
async def connect(self): ...
# Redis construction uses aioredis.from_url(url, decode_responses=True).
```

### Does NOT Exist
- `notify.providers.office365.token_store` does not exist yet.
- Azure token-cache persistence has no Redis/custom backend for this design.

## Implementation Notes

- Do not log token values, cipher keys, or serialized cache text.
- Persistent stores raise `NotifyAuthError` during construction with no cipher key unless plaintext was explicitly enabled.
- Cache corruption is recoverable: warn, delete the bad value, and report a cache miss.

## Acceptance Criteria

- [x] Memory save/load/delete round-trips.
- [x] File data is encrypted with mode `0o600`, and invalid ciphertext is discarded.
- [x] Redis uses the configured prefix/TTL and falls back safely after a connection failure.
- [x] `build_token_store` accepts memory, file, redis, an instance, and `None` defaults.
- [x] `pytest tests/test_office365_token_store.py -q` passes without external Redis.

### Completion Note

Implemented `TokenCipher` (Fernet) and the `TokenStore` ABC with
`MemoryTokenStore`, `FileTokenStore` (0600 writes, corrupt-value deletion),
and `RedisTokenStore` (configurable prefix/TTL, falls back to an in-memory
copy for the rest of the process on any connection error — never blocks or
raises to the caller) plus `build_token_store()`. No test touches a real
Redis server: the Redis tests monkeypatch `_get_redis()` with an in-memory
fake/broken client. Added `tests/test_office365_token_store.py` (10 tests)
— all pass. `flake8` is not installed in this environment; lint could not
be run.
