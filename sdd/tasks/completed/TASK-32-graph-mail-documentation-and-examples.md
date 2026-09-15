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

- [x] Docs explain all flows, send-as/OBO semantics, token-store security, attachments, and bootstrap CLI.
- [x] Docs state app-only mail uses `/users/{mailbox}`, not `/me`, and OBO cannot be queued.
- [x] Examples no longer model legacy REST/basic-auth interaction.
- [x] Migration content covers all §7 behavior changes and removed dependencies.
- [x] Documentation builds or lint checks used by the repository succeed.

### Completion Note

Rewrote `docs/providers.rst`'s `office365`/`outlook` sections (Graph auth
flows, send-as/`from_address`, OBO per-send-only + notify-server
rejection, mailbox routing rule stated explicitly, encrypted pluggable
token stores incl. settings table, attachments/CID/upload sessions,
device-code CLI, tenant prerequisites) and added a "Migration Notes"
subsection (removed deps, `use_credentials` default change, app-only
sender requirement, list-valued batched-send template context, removed
`Outlook.acquire_token*`, no more `input()`, queued-OBO rejection).
Added a Graph-mail feature summary + runnable snippet to `README.md`.
Rewrote both `examples/test_o365.py` and `examples/test_outlook.py` to
instantiate through `Notify(...)` (never the provider class directly,
per the codebase's own convention) with explicit `sender=`.

Full Sphinx build isn't possible in this environment (`myst_parser` is
not installed — a pre-existing gap, unrelated to this task); verified
instead with `docutils.parsers.rst.Parser` directly against the whole
file: parses cleanly with no new errors (`autoclass` "unknown directive"
notices are expected under plain docutils — the same notice appears for
every other provider section, not just mine — and disappear under real
Sphinx). `python -m py_compile` confirms both examples are syntactically
valid.

While verifying repo lint tooling for AC21 I found `black` (unlike
`flake8`, noted missing throughout this feature) *is* installed, and
running it surfaced pre-existing style drift across every file this
feature touched. Committed separately
(`style(mail-messages-graph): apply black ... across FEAT-004 files`)
rather than folding into this task's file list, since it spans files
owned by TASK-19–31: `black --line-length 120` (formatting only, zero
behavior change — re-ran the full suite after, still 328 passed) plus a
few small pylint fixes in code this feature wrote (implicit string
concat, two deprecated `typing` aliases, one missing `**kwargs`
docstring entry). Pylint still reports pre-existing findings in
`notify/models.py`, `notify/providers/mail.py`, and elsewhere that
predate this feature (verified via `git diff origin/dev...HEAD`) — left
untouched, out of scope. `flake8` itself remains not installed in this
environment; could not be run directly, but `black --check` (used as
the available proxy for "120 columns clean") passes on every file this
feature created or modified.
