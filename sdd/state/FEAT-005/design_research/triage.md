# Design Research Triage — FEAT-005

Model: `gpt-5.6-luna` (codex-cli 0.157.0, `model_reasoning_effort=high`)
Run: 2026-09-29T17:11:29Z → 17:16:13Z (4m44s), exit 0, schema-valid, 10 suggestions.
Brief: the accepted exploration document only (`sdd/proposals/lazy-import-providers.proposal.md`
§0/§1, §2.2, §3, §2.1 paths, §5 unresolved) plus the standard question. No spec
draft, no author reasoning, no preferred conclusion, and none of the user's
in-session answers were included.

Path verification: all 10 `affected_paths` sets passed repository containment
and `test -e`.

| # | Suggestion (kind) | Disposition | Reason | Landed in |
|---|---|---|---|---|
| S1 | Make the import graph the measurable acceptance boundary (architecture) | CONFIRM | Matches the measured attribution; turns G6 into a subprocess assertion | spec §2 Overview, §5 G6 |
| S2 | Use a clean subprocess for startup assertions (testing) | CONFIRM | Verified: `tests/test_jinja_string_templates.py:28` and `tests/test_templates_integration.py` import jinja2 at collection time | spec §4 Integration Tests |
| S3 | Treat `Actor` annotation resolution as a compatibility contract (risk) | CONFIRM | PEP 562 cannot rescue `get_type_hints`; repo has zero callers, so the break is documented and tested rather than avoided | spec §7, §5 |
| S4 | Replace capitalize-based class lookup with export-aware resolution (api) | CONFIRM | Reproduced live: `Notify("smtp")` → `module 'notify.providers.smtp' has no attribute 'Smtp'` | spec §3 M1, §5 G2, §6 |
| S5 | Classify only genuine missing-SDK failures as extra errors (api) | CONFIRM | `ModuleNotFoundError.name` adopted as M1's fixed discriminator | spec §3 M1 |
| S6 | Define extras by factory alias and dependency bundle (architecture) | CONFIRM | Verified `Ses.provider=amazon_ses`, `Twilio.provider=sms`, `Aws.provider=aws_email`, smtp has none | spec §2 Data Models, §6 |
| S7 | Complete the migration as a server-aware lockfile change (risk) | CONFIRM | Verified `uv.lock:470-477` and `notify/server` imports of cloudpickle/qw/redis | spec §3 M2, §5 G3 |
| S8 | Add manifest and documentation parity checks (testing) | CONFIRM | Extends the existing `tests/test_office365_configuration.py` pattern | spec §4 Unit Tests |
| S9 | Make compiled-extension state part of the import benchmark contract (testing) | CONFIRM | M1 edits `exceptions.pyx`; a stale `.so` invalidates the G6 measurement | spec §5 G6, §7 |
| S10 | Ship the install-time breaking change with explicit migration notes (risk) | CONFIRM (partial) | Recommendation adopted; its claim that the README states Python 3.8 did NOT verify — README states no version, `pyproject.toml:16` requires `>=3.11` | spec §3 M4 |

Summary: 10 confirmed (1 partial), 0 rejected, 0 escalated.

Note on acceptance: the proposal frontmatter reads `status: review`. The pass
was run because the user resolved all three of the proposal's open forks
in-session and directed the spec to be built from it. Recorded rather than
resolved by editing the proposal.
