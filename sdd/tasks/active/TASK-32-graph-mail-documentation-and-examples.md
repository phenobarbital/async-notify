# TASK-32: Document Microsoft Graph mail flows and update examples

**Feature**: FEAT-004 — Mail Messages via Microsoft Graph (send-as & On-Behalf-Of)
**Spec**: `sdd/specs/mail-messages-graph.spec.md`
**Status**: pending
**Priority**: medium
**Estimated effort**: M (2–4h)
**Depends-on**: TASK-20, TASK-27, TASK-28, TASK-29, TASK-30
**Assigned-to**: unassigned

---

## Context

The current provider documentation incorrectly describes Graph behavior while the implementation uses legacy APIs. Users need copyable Graph examples, tenant prerequisites, token-store guidance, and migration notes for the behavioral changes. Implements spec §3 M11, AC10–AC17, and the §7 release-note requirements.

## Scope

- Rewrite Office365 and Outlook provider documentation around Graph, four auth flows, sender/from override, OBO direct-send-only rules, attachment behavior, and device-code bootstrap.
- Document tenant/app permissions, OBO audience and consent requirements, application access policy/RBAC scoping, and persistent-cache encryption/TTL.
- Update README provider material and both examples to instantiate through `Notify` where user-facing.
- Add migration/release notes: removed REST libraries/API, changed `use_credentials` default, app-only sender requirement, and list-valued template context.

**NOT in scope**: automatic Azure tenant administration, changing documentation tooling, or logging a deprecation warning for the Outlook alias.

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `docs/providers.rst` | MODIFY | Accurate Office365/Outlook Graph provider reference. |
| `README.md` | MODIFY | Graph-mail feature and migration summary. |
| `examples/test_o365.py` | MODIFY | Safe Graph Office365 example. |
| `examples/test_outlook.py` | MODIFY | Notify-factory Outlook alias example. |

## Codebase Contract (Anti-Hallucination)

### Verified Imports
```python
from notify import Notify  # notify/notify.py:18-48
```

### Existing Signatures to Use
```python
# docs/providers.rst:220-240 and 467-487
# Existing Office365 and Outlook provider documentation locations.

# examples/test_o365.py:24 and examples/test_outlook.py:24
# Current examples instantiate Office365/Outlook with legacy credential behavior.
```

### Does NOT Exist
- Queued OBO support does not exist; documentation must say assertions are rejected by notify-server.
- The Outlook alias does not emit a deprecation warning.
- Existing docs do not accurately describe the current provider implementation.

## Implementation Notes

- Do not include real credentials, assertions, client secrets, certificate passwords, token-cache blobs, or tenant identifiers.
- Make the examples asynchronous, factory-based, and explicit about app-only `sender`.
- Place migration details in the existing README and provider documentation; do not create a new documentation convention as part of this task.

## Acceptance Criteria

- [ ] Docs explain all flows, send-as/OBO semantics, token-store security, attachments, and bootstrap CLI.
- [ ] Docs state app-only mail uses `/users/{mailbox}`, not `/me`, and OBO cannot be queued.
- [ ] Examples no longer model legacy REST/basic-auth interaction.
- [ ] Migration content covers all §7 behavior changes and removed dependencies.
- [ ] Documentation builds or lint checks used by the repository succeed.
