# TASK-25: Add opt-in batch and error hooks to ProviderEmail

**Feature**: FEAT-004 — Mail Messages via Microsoft Graph (send-as & On-Behalf-Of)
**Spec**: `sdd/specs/mail-messages-graph.spec.md`
**Status**: pending
**Priority**: high
**Estimated effort**: S (< 2h)
**Depends-on**: none
**Assigned-to**: unassigned

---

## Context

Office365 must send one Graph message to all recipients while preserving every other email provider’s behavior. These opt-in hooks keep the public `send()` implementation centralized. Implements spec §3 M5 and AC6/AC9.

## Scope

- Add `batch_recipients`, `raise_errors`, and `redacted_send_kwargs` defaults to `ProviderEmail`.
- Update `send()` to batch exactly once, selectively re-raise declared errors, and remove declared callback kwargs.
- Add dummy-provider tests proving existing default behavior is unchanged.

**NOT in scope**: overriding `send()` in Office365/Outlook, changing SES’s override, or changing callback APIs beyond secret redaction.

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `notify/providers/mail.py` | MODIFY | Add and honor the opt-in hooks. |
| `tests/test_mail_hooks.py` | CREATE | Default, batch, error, and callback-redaction tests. |

## Codebase Contract (Anti-Hallucination)

### Verified Imports
```python
from notify.models import Actor                  # notify/providers/mail.py:8
from notify.exceptions import ProviderError      # notify/providers/mail.py:9
from .base import ProviderBase, ProviderType     # notify/providers/mail.py:11
```

### Existing Signatures to Use
```python
# notify/providers/mail.py:15,22-24,209-257
class ProviderEmail(ProviderBase, ABC): ...
async def send(self, recipient: list[Actor] = None, message=None, subject: str = None, **kwargs): ...

# notify/providers/base.py:226-251
async def __sent__(self, to, message, result, **kwargs): ...
```

### Does NOT Exist
- `batch_recipients`, `raise_errors`, and `redacted_send_kwargs` are not yet attributes of `ProviderEmail`.
- This feature must not add a second public send path.

## Implementation Notes

- Defaults must exactly preserve current per-recipient calls and swallowed exceptions.
- In batch mode invoke `_send_` and `__sent__` once with the recipient list.
- Log a selected delivery exception before re-raising it, and remove redacted kwargs only for callbacks.

## Acceptance Criteria

- [x] Existing providers retain their current behavior by default.
- [x] Batched sending produces one result and one callback invocation.
- [x] Declared connect and delivery exceptions propagate unchanged.
- [x] `user_assertion` can be withheld from callbacks.
- [x] `pytest tests/test_mail_hooks.py -q` passes.

### Completion Note

Added `batch_recipients`, `raise_errors`, `redacted_send_kwargs` class
attributes to `ProviderEmail` with the specified defaults (`False`, `()`,
`frozenset()`). `send()` gained an `except self.raise_errors as err: ...;
raise` branch (evaluated at runtime against the instance attribute — an
empty tuple never matches, so default behavior is untouched) around both
`connect()` and the per-recipient/batch send path, and a `batch_recipients`
branch that calls `_send_` once with the full recipient list and
`__sent__` once. `redacted_send_kwargs` filters only the kwargs forwarded
to `__sent__`/the `sent` callback; `_send_` itself still receives the
unredacted kwargs. Added `tests/test_mail_hooks.py` (6 tests via a
`_DummyMailProvider` subclass) — all pass. Verified `tests/test_email_utf8.py`
(the real `ProviderEmail.send()` path, no hooks touched) — 15/15 still
pass. `tests/test_ses.py` has 2 pre-existing failures
(`botocore.exceptions.InvalidRegionError` on `region_name='mock_region'`)
unrelated to this change: `Ses.send()` fully overrides `ProviderEmail.send()`
and never calls `super().send()` (verified at `ses.py:158`), so these
hooks cannot affect it; confirmed by diffing `notify/providers/mail.py`
against `origin/dev` — the diff touches only the new class attributes and
`send()`. `flake8` is not installed in this environment; lint could not
be run.
