# TASK-27: Implement Office365 rendering and Graph message dispatch

**Feature**: FEAT-004 — Mail Messages via Microsoft Graph (send-as & On-Behalf-Of)
**Spec**: `sdd/specs/mail-messages-graph.spec.md`
**Status**: pending
**Priority**: high
**Estimated effort**: M (2–4h)
**Depends-on**: TASK-23, TASK-24, TASK-25, TASK-26
**Assigned-to**: unassigned

---

## Context

With lifecycle and Graph primitives in place, Office365 must render once for a full recipient list and dispatch exactly one Graph message, including send-as and OBO constraints. Implements send portion of spec §3 M6 and AC3, AC4, AC6–AC9.

## Scope

- Implement `_render_` and `_send_` on the rewritten Office365 provider.
- Render once with list-valued `recipient`/`username`; use `body` or `message` without a template.
- Extract per-send mail arguments from a copy, resolve app-only/delegated/OBO mailbox routing, and invoke `GraphMailSender`.
- Bind OBO assertion only around sending; warn when assertions are supplied to another flow.
- Extend provider tests for routing, send-as, OBO, result shape, and callback redaction.

**NOT in scope**: flow construction, SDK sender internals, the Outlook alias, or queued-message rejection.

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `notify/providers/office365/office365.py` | MODIFY | Add rendering and dispatch behavior. |
| `tests/test_office365_provider.py` | MODIFY | Add mocked dispatch behavior tests. |

## Codebase Contract (Anti-Hallucination)

### Verified Imports
```python
from notify.models import Actor, MailSendResult
from notify.providers.office365.credential import AuthFlow
from notify.providers.office365.graph_mail import GraphMailSender, build_message, load_attachments
from notify.exceptions import NotifyAuthError
```

### Existing Signatures to Use
```python
# Office365 target signatures from spec §3 M6
async def _render_(self, to: list[Actor] = None, message: str = None, subject: str = None, **kwargs) -> str: ...
async def _send_(self, to: list[Actor], message: str, subject: str = None, **kwargs) -> MailSendResult: ...

# notify/providers/base.py:155-166
# self._template is set by _prepare_ and supports render_async().
```

### Does NOT Exist
- Existing Office365 only renders one legacy Outlook REST message per recipient.
- App-only Graph sending through `/me` is forbidden.

## Implementation Notes

- Do not mutate the kwargs received by the framework; copy before popping supported send options.
- App-only requires mailbox from `from_address` or `sender`; delegated/OBO use `/me` and populate `Message.from_` when requested.
- `NotifyAuthError` must leave `ProviderEmail.send()` through TASK-25’s hook while delivery failures remain result values.

## Acceptance Criteria

- [ ] A multi-recipient `send()` returns one `MailSendResult` covering all addresses.
- [ ] App-only routes through `/users/{mailbox}` and OBO/delegated route through `/me`.
- [ ] OBO requires a per-send assertion and scopes it to the credential context.
- [ ] `from_address` overrides the instance sender and callback data contains no assertion.
- [ ] Provider dispatch tests pass offline.
