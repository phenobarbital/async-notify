# TASK-24: Implement Graph mail delivery and upload sessions

**Feature**: FEAT-004 — Mail Messages via Microsoft Graph (send-as & On-Behalf-Of)
**Spec**: `sdd/specs/mail-messages-graph.spec.md`
**Status**: pending
**Priority**: high
**Estimated effort**: M (2–4h)
**Depends-on**: TASK-23
**Assigned-to**: unassigned

---

## Context

This task executes the typed Graph mail message produced by TASK-23. It selects direct `sendMail` for small requests and a draft/upload/send workflow for larger files while preserving the specification’s error taxonomy. Implements sender portion of §3 M4 and AC7–AC9.

## Scope

- Implement `GraphMailSender.send` and `map_odata_error` in `graph_mail.py`.
- Route app-only mail through `/users/{mailbox}` and delegated/OBO mail through `/me`.
- Implement direct send, draft creation, upload session, best-effort draft deletion, and Sent Items warning behavior.
- Add mocked small, large, failure, and auth-error tests.

**NOT in scope**: message construction, token acquisition, or provider-level mailbox resolution.

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `notify/providers/office365/graph_mail.py` | MODIFY | Add sender, strategies, and error mapping. |
| `tests/test_office365_graph.py` | MODIFY | Add fully mocked sender tests. |

## Codebase Contract (Anti-Hallucination)

### Verified Imports
```python
from msgraph import GraphServiceClient
from notify.models import MailSendResult, OutboundAttachment  # created by TASK-23
from notify.exceptions import NotifyAuthError
```

### Existing Signatures to Use
```python
# Graph builders verified in spec §6
graph.me
graph.users.by_user_id(mailbox)
graph.request_adapter
# Both user routes expose send_mail.post and messages builders.
```

### Does NOT Exist
- `save_to_sent_items` is not available on a draft message `send.post()` request.
- `ErrorInvalidUser` is not an authentication error in this feature.

## Implementation Notes

- Use `INLINE_REQUEST_LIMIT = 3 * 1024 * 1024` and 150 MB per attachment exactly.
- Authentication/permission responses raise `NotifyAuthError`; other Graph failures return failed `MailSendResult` values.
- Do not leak Graph response secrets or request content in errors.

## Acceptance Criteria

- [ ] A small request makes one `send_mail.post` with `save_to_sent_items`.
- [ ] A large request creates a draft, uploads remaining files, and sends it.
- [ ] Failed upload/send attempts delete the draft best effort.
- [ ] 401/403 and configured permission codes raise; invalid recipients return failure result.
- [ ] Mocked graph sender tests pass offline.
