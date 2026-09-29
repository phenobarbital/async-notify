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

- [x] A multi-recipient `send()` returns one `MailSendResult` covering all addresses.
- [x] App-only routes through `/users/{mailbox}` and OBO/delegated route through `/me`.
- [x] OBO requires a per-send assertion and scopes it to the credential context.
- [x] `from_address` overrides the instance sender and callback data contains no assertion.
- [x] Provider dispatch tests pass offline.

### Completion Note

Implemented `_render_` (renders once with `recipient`/`username` bound to
the full `to` list when a template is set; otherwise `kwargs["body"]` or
`message`) and `_send_` (pops `user_assertion`/`cc`/`bcc`/`reply_to`/
`importance`/`attachments`/`inline_images`/`from_address`/
`save_to_sent_items` from a *copy* of kwargs, renders, loads attachments,
builds the Graph message, and dispatches via `GraphMailSender`).
Mailbox routing: `AuthFlow.CLIENT_CREDENTIALS` is the only "app-only" flow
and always resolves `mailbox = from_address or sender`, raising
`NotifyAuthError` if both are absent; every other flow (`delegated`,
`on_behalf_of`, the legacy `password`/ROPC flow) routes through `/me`
(`mailbox=None`) since all three represent a specific signed-in user, not
an app-only token — the spec text names only "app-only" vs "Delegated/OBO"
explicitly; ROPC is grouped with the delegated/OBO `/me` case by
elimination, since app-only is defined as exactly the `client_credentials`
flow. `on_behalf_of` wraps the `GraphMailSender.send` call in
`self._credential.use_assertion(user_assertion)`, raising `NotifyAuthError`
when the assertion is missing; an assertion passed to any other flow is
dropped with a `self.logger.warning` instead of being forwarded to Graph.
Extended `tests/test_office365_provider.py` with a `_FakeGraphMailSender`
(patched in via an autouse fixture, so no real Graph HTTP call is ever
made) and 9 new tests (app-only missing-mailbox raise, app-only
`/users/{id}` routing, `from_address` override, delegated `/me` routing,
OBO `/me` + assertion scoping verified via
`credential._current_assertion.get()` inside the fake sender,
OBO-without-assertion raise, assertion-on-non-OBO warns+ignored,
multi-recipient → one `MailSendResult`, and `user_assertion` never
reaching the `sent` callback) — 20 tests in the file total, all pass.
Full-suite run unchanged from TASK-26's baseline (298 passed; only the
same pre-existing, untouched `test_ses.py` ×2 and `test_outlook1.py` ×3
failures). `flake8` is not installed in this environment; lint could not
be run.
