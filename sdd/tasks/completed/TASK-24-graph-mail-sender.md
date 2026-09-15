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

- [x] A small request makes one `send_mail.post` with `save_to_sent_items`.
- [x] A large request creates a draft, uploads remaining files, and sends it.
- [x] Failed upload/send attempts delete the draft best effort.
- [x] 401/403 and configured permission codes raise; invalid recipients return failure result.
- [x] Mocked graph sender tests pass offline.

### Completion Note

Added `GraphMailSender` and `map_odata_error` to
`notify/providers/office365/graph_mail.py`. `send()` picks `send_mail` vs
`draft_upload` by total attachment size against `INLINE_REQUEST_LIMIT`;
`_route()` uses `graph.users.by_user_id(mailbox)` when a mailbox is given,
else `graph.me`. `draft_upload` keeps inline images and small files
embedded on the draft (`_select_embedded_indices`, inline-first),
uploads the rest through `create_upload_session` + `LargeFileUploadTask`,
then sends the draft; any failure during upload/send deletes the draft
best-effort (its own exception is swallowed and logged) before
re-raising the original error. `map_odata_error` raises `NotifyAuthError`
for 401/403 or `AUTH_ERROR_CODES`, otherwise returns a failed
`MailSendResult`. Extended `tests/test_office365_graph.py` with a fake
Graph route builder (`_FakeRouteBuilder`) and a patched
`LargeFileUploadTask` (8 new tests: small send, large draft/upload/send,
`save_to_sent_items=False` warning, draft deletion on upload failure,
401/403 → raise, 400 → failed result, `ODataError` from `send_mail.post`
→ raise) — 25 tests in the file total, all pass. `flake8` is not
installed in this environment; lint could not be run.
