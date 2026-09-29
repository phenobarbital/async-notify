# TASK-36: Document the extras matrix and the 1.7.0 install migration

**Feature**: FEAT-005 — Actionable optional-dependency diagnostics and a slim core install
**Spec**: `sdd/specs/lazy-import-providers.spec.md`
**Status**: pending
**Priority**: high
**Estimated effort**: S (< 2h)
**Depends-on**: TASK-33
**Assigned-to**: unassigned

---

## Context

Implements **spec §3 Module 4**, serving goal **G5**.

TASK-33 makes this an **install-time breaking change**: after it lands,
installing `async-notify` no longer ships `aiobotocore`, `emoji`, `cloudpickle`
or `pillow`, and the `notify` console script stops working without the new
`server` extra. The user accepted that during proposal Q&A (U3) **on condition of
release notes** — so this task is not optional, and spec §7 says so explicitly.

Priority is high despite the small size: TASK-38's
`test_readme_matrix_matches_manifest` asserts README ↔ manifest parity, so this
task gates that one.

---

## Scope

- Add an **Installation** section to `README.md` with a provider → extra table
  covering **all 17** providers, including those that need no extra.
- Document the `all` and `server` extras as install targets.
- State that the `notify` console script requires the `server` extra.
- Add a `1.7.0` entry to `CHANGES.rst` listing every package that left core, the
  extra that now carries it, and the one-line remediation.
- Record the accepted `typing.get_type_hints()` behaviour change (see below).
- Correct `README.md:14` — it claims Python >= 3.8; `pyproject.toml:16` requires >= 3.11.

**NOT in scope**: `pyproject.toml` (TASK-33 owns it — this task *describes* it);
any change under `notify/`; the parity test itself (TASK-38); reducing the
install weight of `all` (spec §1 Non-Goals); bumping `notify/version.py`
(the `/release` flow owns version bumps).

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `README.md` | MODIFY | New "Installation" section + extras matrix; fix the Python floor |
| `CHANGES.rst` | MODIFY | New 1.7.0 entry at the top |

---

## Codebase Contract (Anti-Hallucination)

> Verified against `dev` @ `d72fe6e` on 2026-09-29.

### Verified current state

```markdown
# README.md
# Async-Notify #                          <- line 1
### Why Async-Notify? ###                 <- line 7
### Requirements ###                      <- line 12
* Python >= 3.8                           <- line 14   (WRONG — see below)
### Quick Tutorial ###                    <- line 17   (provider bullet list, lines 19-29)
### Templates ###                         <- line 31
### Microsoft Graph mail (`office365` / `outlook`) ###   <- line 65
### How do I get set up? ###              <- line 109
### License ###                           <- line 130
```

```rst
.. CHANGES.rst
ChangeLog        <- line 1
=========        <- line 2
                 <- line 3
.. _v0.6.0:      <- line 4   (newest entry is 0.6.0, 2022-09-27 — the file is stale)
```

```toml
# pyproject.toml:16
requires-python = ">=3.11"
# pyproject.toml:9-12 — distribution name is `async-notify`; import package is `notify`
# pyproject.toml:145-146
[project.scripts]
notify = "notify.__main__:main"
```

`notify/__main__.py:4` is `from notify.server import NotifyWorker` — verified; this
is why the console script needs the `server` extra.

Current version: `notify/version.py:9` → `__version__ = "1.6.1"`. Spec target: **1.7.0**.

### The 17 providers and their extras (spec §6, verified by AST scan)

| Factory alias | Extra | | Factory alias | Extra |
|---|---|---|---|---|
| `aws` | *(none needed)* | | `sendgrid` | *(none needed)* |
| `dialpad` | *(core — aiohttp)* | | `ses` | `ses` |
| `dummy` | *(none needed)* | | `slack` | `slack` |
| `email` | *(none needed)* | | `smtp` | *(none needed)* |
| `gmail` | `google` | | `teams` | `azure` |
| `office365` | `azure` | | `telegram` | `telegram` |
| `onesignal` | `push` | | `twilio` | `twilio` |
| `outlook` | `azure` | | `xmpp` | `xmpp` |
| | | | `zoom` | *(core — aiohttp)* |

Plus the non-provider extras: `all`, `server`, `uvloop`, `templates`, `default`, `dev`.

### Packages leaving core in 1.7.0 (TASK-33)

| Package | Was | Now in | Remediation extra |
|---|---|---|---|
| `aiobotocore` | core | `ses` | `ses` |
| `emoji` | core | `telegram` | `telegram` |
| `cloudpickle` | core | `server` | `server` |
| `pillow` | core | **removed entirely** | none — nothing under `notify/` imports PIL |
| `aiohttp` | *(transitive)* | **promoted to core** | none |

### Does NOT Exist

- ~~an "Installation" section in `README.md`~~ — **this task creates it**.
- ~~a 1.7.0 entry in `CHANGES.rst`~~ — the newest is 0.6.0 (2022-09-27).
- ~~a Python 3.8 floor~~ — `pyproject.toml:16` requires `>=3.11`. README line 14 is
  stale and must be corrected.
- ~~`pillow` moving to an extra~~ — it is deleted, not relocated.

---

## Implementation Notes

### A correction to the spec's own record

Spec §9 triages design-research suggestion **S10** as `CONFIRM (partial)`, rejecting
its supporting claim on the grounds that "the README states no Python version".
That rebuttal is wrong: `README.md:14` reads `* Python >= 3.8`. The suggestion's
substance stands, so fix the line to `>= 3.11` to match `pyproject.toml:16`, and
say so in your Completion Note. Do not edit the spec.

### Key Constraints

- README is GitHub-flavoured Markdown with `### Heading ###` style — match it.
- `CHANGES.rst` is reStructuredText with `.. _vX.Y.Z:` anchors and `---` underlines
  — match the existing entries' shape exactly, and put 1.7.0 **at the top**
  (the file is newest-first).
- Every extra name you write must match `pyproject.toml` **exactly** — TASK-38
  asserts bidirectional parity and a typo fails it.
- Distribution name is `async-notify`; the import package is `notify`. Install
  commands name the former.

---

## Implementation Blueprint

### Steps (in order)

1. Fix the Python floor on README line 14 — *why*: it contradicts
   `pyproject.toml:16` and sits in the section the new Installation text adjoins.
2. Insert the Installation section after `### Requirements ###` — *why*: a reader
   hitting a missing-SDK error needs the matrix before the tutorial, and this is
   where an installation section is conventionally looked for.
3. Add the 1.7.0 entry at the top of `CHANGES.rst` — *why*: G5's migration half;
   an install-time breaking change with no release note is the failure mode the
   user conditioned acceptance on.

### `README.md` (MODIFY — the Python floor)

```markdown
# occurrences: 1 (verified: grep -c 'Python >= 3.8' README.md)
# REPLACE line 14 (verified: README.md:14)
* Python >= 3.11
```
**Why**: `pyproject.toml:16` is `requires-python = ">=3.11"`; the installer already
refuses 3.8, so the README is simply wrong.

### `README.md` (MODIFY — the Installation section)

```markdown
# occurrences: 1 (verified: grep -c '^### Quick Tutorial ###' README.md)
# BEFORE — insert this whole section above `### Quick Tutorial ###`
# (verified: README.md:17), i.e. directly after the Requirements bullets.

### Installation ###

The core install is deliberately slim: it carries only what the
provider-agnostic core path needs. Providers that depend on a third-party SDK
ship that SDK in an **extra** — install `async-notify[<extra>]` for one
provider, `async-notify[all]` for every provider, or `async-notify[server]`
for the Redis-backed notify server.

<!-- FILL IN: the provider -> extra table, one row per alias, all 17 rows from
     the Codebase Contract above, in alphabetical order. Columns:
     | Provider | `Notify(...)` alias | Extra required |
     Rows needing no extra say so explicitly (e.g. "none — core install").
     Show the concrete install command form once, above the table.
     Bounded by AC-G5 ("covering all 17 providers") and by TASK-38's
     test_readme_matrix_matches_manifest — every extra name must match
     pyproject.toml verbatim. -->

The `notify` console script (`notify/__main__.py`) starts the Redis-backed
notification server and therefore **requires the `server` extra**; without it
the script exits with an import error for `cloudpickle`.
```
**Why this shape**: AC-G5 fixes the three required elements — a matrix covering all
17 providers *including* the ones needing no extra, the `all` and `server` targets,
and the console-script note. Keeping the "no extra" rows in the table is what makes
it answer "do I need anything?" rather than only "what do I install?". The alias
column matters because that string is what `Notify()` takes and what TASK-34's error
message echoes back to the user.

### `CHANGES.rst` (MODIFY)

```rst
# occurrences: 1 (verified: grep -c '^=========$' CHANGES.rst)
# AFTER — insert directly below the `=========` underline (verified: CHANGES.rst:2),
# above `.. _v0.6.0:`, so the file stays newest-first.

.. _v1.7.0:

1.7.0 (unreleased)
------------------

*Slimmer core install (breaking at install time):*

    The following packages are no longer installed with the base distribution.
    Install the extra that now carries the one you need:

    - ``aiobotocore`` (Amazon SES) -> extra ``ses``
    - ``emoji`` (Telegram) -> extra ``telegram``
    - ``cloudpickle`` (notify server) -> extra ``server``
    - ``pillow`` -> removed entirely; nothing in ``notify`` imported it.

    ``aiohttp`` is now a core dependency (``dialpad``, ``zoom`` and ``teams``
    import it directly and it previously arrived only transitively).

    The ``notify`` console script now requires the ``server`` extra.

    New per-provider extras: ``ses``, ``slack``, ``twilio``, ``xmpp``, plus
    ``server`` for the Redis-backed worker.

*Actionable missing-dependency errors:*

    - A provider whose optional SDK is missing now raises
      ``notify.exceptions.ProviderDependencyError`` naming the missing module and
      the exact extra to install. It subclasses ``ProviderError``, so existing
      ``except ProviderError`` handlers are unaffected.
    - An unknown provider name still raises plain ``ProviderError``, now listing
      the known aliases.

*Fixes:*

    - ``Notify("smtp")`` works. Provider classes are resolved through the
      package's ``__all__`` instead of ``provider.capitalize()``, which asked for
      a non-existent ``Smtp``.

*Faster import:*

    - ``import notify`` no longer pulls in ``jinja2`` or ``datamodel``; both load
      on first template use.
    - **Behaviour change**: ``typing.get_type_hints()`` on ``ProviderBase`` and
      ``ThreadMessage`` methods no longer resolves the ``Actor`` annotation, which
      is now a deferred (``TYPE_CHECKING``) import. Import ``notify.models.Actor``
      explicitly if you evaluate those hints at runtime.
```
**Why**: AC-G5 asks for "each package that left core, the extra that now carries it,
and the one-line remediation" — the first block is literally that. The
`get_type_hints` note is spec §7's mitigation for TASK-35's accepted behaviour
change: recording it is what makes it a decision rather than a surprise. Mark the
entry `(unreleased)`; the `/release` flow sets the date.

### FILL IN checklist

- [ ] `README.md` Installation — the 17-row provider → extra table; bounded by
      AC-G5 and TASK-38's `test_readme_matrix_matches_manifest`.

---

## Acceptance Criteria

- [ ] README has an Installation section listing all **17** providers with the
      extra each needs (rows needing none say so). *(AC-G5)*
- [ ] README documents the `all` and `server` extras, and states the `notify`
      console script requires `server`. *(AC-G5)*
- [ ] Every extra named in README exists in `pyproject.toml`, and every non-`dev`
      extra in `pyproject.toml` appears in README. *(gates TASK-38)*
- [ ] `README.md` no longer claims Python >= 3.8.
- [ ] `CHANGES.rst` has a 1.7.0 entry naming each package that left core, its new
      extra, and the remediation. *(AC-G5)*
- [ ] `CHANGES.rst` records the `typing.get_type_hints()` behaviour change. *(spec §7)*
- [ ] `CHANGES.rst` still parses as reStructuredText, and 1.7.0 is the first entry.

---

## Test Specification

No test file in this task — TASK-38 owns `test_readme_matrix_matches_manifest`.
Self-check the parity it will assert:

```bash
source .venv/bin/activate
python - <<'PY'
import tomllib
extras = set(tomllib.load(open("pyproject.toml", "rb"))["project"]["optional-dependencies"]) - {"dev"}
readme = open("README.md", encoding="utf-8").read()
missing = {e for e in extras if f"async-notify[{e}]" not in readme and f"`{e}`" not in readme}
print("extras absent from README:", missing or "none")
PY
grep -n "Python >= " README.md
head -8 CHANGES.rst
```

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** §3 Module 4, §5 (G5) and §7.
2. **Check dependencies** — TASK-33 must be in `sdd/tasks/completed/`; read the
   **landed** `pyproject.toml` and take the extra names from it, not from this task.
3. **Verify the Codebase Contract** — re-read `README.md:1-35` and `CHANGES.rst:1-10`.
4. Update this feature's index entry to `in-progress`.
5. **Implement** from the blueprint; resolve the `FILL IN`.
6. **Verify** every acceptance criterion.
7. **Move this file** to `sdd/tasks/completed/`.
8. **Update** `sdd/tasks/index/lazy-import-providers.json` → `"done"`.
9. **Fill in the Completion Note**, including the README Python-floor correction.

---

## Completion Note

*(Agent fills this in when done)*

**Completed by**: <session or agent ID>
**Date**: YYYY-MM-DD
**Notes**:

**Deviations from spec**: corrected `README.md:14` from "Python >= 3.8" to
">= 3.11". Spec §9's S10 triage claims the README states no Python version; it does.
