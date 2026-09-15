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

- [ ] `Notify("outlook")` creates an `Outlook` that is an `Office365` subclass.
- [ ] Queued files attach once; missing paths raise `FileNotFoundError` at `add_attachment`.
- [ ] Legacy REST imports and direct token methods are absent.
- [ ] Rewritten Outlook tests pass offline.
