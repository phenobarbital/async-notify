# TASK-28: Replace Outlook with the Graph Office365 alias

**Feature**: FEAT-004 — Mail Messages via Microsoft Graph (send-as & On-Behalf-Of)
**Spec**: `sdd/specs/mail-messages-graph.spec.md`
**Status**: pending
**Priority**: medium
**Estimated effort**: S (< 2h)
**Depends-on**: TASK-27
**Assigned-to**: unassigned

---

## Context

`Notify("outlook")` must remain valid without the broken Office365 REST client. The compatibility surface is an `Office365` subclass plus its existing queued-attachment API. Implements spec §3 M7 and AC1/AC17.

## Scope

- Rewrite `Outlook` as a silent `Office365` subclass with `provider = "outlook"`.
- Retain asynchronous `add_attachment`, queue paths for the next send, validate missing paths immediately, and clear queued values after dispatch.
- Remove legacy REST token methods/imports and update package exports if needed.
- Add offline factory/subclass/queue regression tests.

**NOT in scope**: deprecation warnings, different authentication behavior, or a separate Outlook Graph implementation.

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `notify/providers/outlook/outlook.py` | MODIFY | Graph-core compatibility alias. |
| `notify/providers/outlook/__init__.py` | MODIFY | Accurate alias export documentation. |
| `tests/test_outlook.py` | MODIFY | Replace REST assumptions with alias tests. |
| `tests/test_outlook1.py` | MODIFY | Replace REST assumptions with alias tests. |

## Codebase Contract (Anti-Hallucination)

### Verified Imports
```python
from notify.providers.office365.office365 import Office365
from notify.models import Actor, MailSendResult
```

### Existing Signatures to Use
```python
# notify/providers/outlook/outlook.py:22,29,103
class Outlook(ProviderEmail):
    provider = "outlook"
    async def add_attachment(self, filename): ...

# notify/notify.py:31-48,70-86
# Notify dynamically imports notify.providers.<provider> and resolves provider.capitalize().
```

### Does NOT Exist
- `Outlook.acquire_token` and `Outlook.acquire_token_by_username` must not remain.
- The rewritten alias must not import `office365.graph_client`, `O365`, or `pyo365`.

## Implementation Notes

- Store queued attachment paths privately and merge them with explicit per-send attachments.
- Clear the queue after each attempt so later messages do not receive stale files.

## Acceptance Criteria

- [x] `Notify("outlook")` creates an `Outlook` that is an `Office365` subclass.
- [x] Queued files attach once; missing paths raise `FileNotFoundError` at `add_attachment`.
- [x] Legacy REST imports and direct token methods are absent.
- [x] Rewritten Outlook tests pass offline.

### Completion Note

Rewrote `Outlook` as a silent `Office365` subclass (`provider = "outlook"`),
removing the `office365.graph_client.GraphClient` import and the
`acquire_token`/`acquire_token_by_username` methods entirely.
`add_attachment(filename)` keeps its async signature and now queues
`Path` objects in `self._pending_attachments` (raising `FileNotFoundError`
immediately for a missing path); `_send_` merges the queue into
`kwargs['attachments']`, delegates to `Office365._send_`, and clears the
queue in a `finally` block (so it clears even when the send raises).
Rewrote `tests/test_outlook1.py` (13 tests: subclass identity, context
manager, network-free `connect()`, required legacy attributes, removed
REST methods/imports, attachment queueing, merge-and-clear on success,
and clear-on-failure) — all pass; `async def outlook()` fixture, not a
plain `def`, because a sync fixture constructing a `ProviderBase` subclass
hits the same pre-existing uvloop/event-loop-ordering issue noted in
TASK-26 (this was in fact the root cause of the `test_outlook1.py`
`RuntimeError` errors seen in earlier full-suite runs — now fixed as a
side effect of this rewrite). `tests/test_outlook.py`
(`BaseTestCase`-based) needed no content changes — it already only
exercises `connect()`/`close()`/context-manager/required-attributes, all
still valid — and passes unchanged. Full-suite run
(`pytest tests/ --ignore=tests/integration`): 307 passed, only the same
pre-existing, unrelated `test_ses.py` ×2 failures remain. `flake8` is not
installed in this environment; lint could not be run.
