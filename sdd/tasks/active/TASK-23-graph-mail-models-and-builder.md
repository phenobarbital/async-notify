# TASK-23: Add Graph mail models and message builder

**Feature**: FEAT-004 — Mail Messages via Microsoft Graph (send-as & On-Behalf-Of)
**Spec**: `sdd/specs/mail-messages-graph.spec.md`
**Status**: pending
**Priority**: high
**Estimated effort**: M (2–4h)
**Depends-on**: none
**Assigned-to**: unassigned

---

## Context

Graph message construction needs typed result/attachment models and a deterministic translation of recipients, headers, files, and CID images into Graph models. Implements the builder portion of spec §3 M4 and AC6–AC8.

## Scope

- Add `OutboundAttachment` and `MailSendResult` as `datamodel.BaseModel` classes.
- Create asynchronous attachment loading with content-type detection, inline CID handling, 3 MB aggregate metadata, and 150 MB per-file rejection.
- Implement recipient flattening and `build_message` for HTML body, CC/BCC/Reply-To, importance, from address, and file attachments.
- Add offline model/builder tests.

**NOT in scope**: Graph request execution, upload sessions, provider rendering, or MSAL credentials.

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `notify/models.py` | MODIFY | Add Graph outbound attachment and send-result models. |
| `notify/providers/office365/graph_mail.py` | CREATE | Attachment loading, recipient conversion, and message construction. |
| `tests/test_office365_graph.py` | CREATE | Builder and attachment tests. |

## Codebase Contract (Anti-Hallucination)

### Verified Imports
```python
from datamodel import BaseModel, Field                   # notify/models.py:9
from notify.models import Actor                          # notify/providers/mail.py:8
from notify.exceptions import ProviderError, NotifyAuthError
```

### Existing Signatures to Use
```python
# notify/models.py:28-50,96-137
class Account(BaseModel):  # address supports str | list[str]
class Actor(BaseModel):    # name and optional account
class Attachment(BaseModel): ...
class MailAttachment(Attachment): ...
```

### Does NOT Exist
- `OutboundAttachment` and `MailSendResult` do not exist in `notify.models`.
- Existing providers do not implement CC, BCC, reply-to, inline CID, or `from_address` handling.

## Implementation Notes

- Read paths with `aiofiles`; do not block the event loop.
- Preserve a missing CID reference as a warning and an unreferenced inline image as an attachment with debug logging.
- Invalid importance raises `ValueError`; unknown content types use `application/octet-stream`.

## Acceptance Criteria

- [ ] Actor addresses, including address lists, become Graph recipients correctly.
- [ ] Header fields and importance map to Graph models.
- [ ] CID and attachment size rules match spec §3 M4.
- [ ] `pytest tests/test_office365_graph.py -q` passes for builder cases.
