# TASK-33: Slim the core install and add a per-provider extra for every SDK

**Feature**: FEAT-005 — Actionable optional-dependency diagnostics and a slim core install
**Spec**: `sdd/specs/lazy-import-providers.spec.md`
**Status**: pending
**Priority**: high
**Estimated effort**: M (2-4h)
**Depends-on**: none
**Assigned-to**: unassigned

---

## Context

Implements **spec §3 Module 2 — Dependency manifest**, serving goals **G3** and **G4**.

`pip install async-notify` currently drags in four packages the core path never
uses: `pillow` (imported *nowhere* under `notify/`), `emoji` (telegram only),
`aiobotocore` (ses only) and `cloudpickle` (`notify/server` only). At the same
time four providers (`ses`, `slack`, `twilio`, `xmpp`) and the whole server
subsystem have no extra at all, so TASK-34's diagnostic message would have no
precise extra name to cite.

This task runs **first** in the feature: TASK-34's error messages and TASK-36's
README matrix are both keyed off the extras defined here.

---

## Scope

- Remove `pillow`, `emoji`, `aiobotocore` and `cloudpickle` from `[project] dependencies`.
- **Promote `aiohttp>=3.10` into core.** `dialpad`, `zoom` and `teams` import it
  directly, and it currently arrives only transitively via `aiobotocore` — which
  this task removes from core. Without this promotion those three providers break.
- Add five new extras: `ses`, `slack`, `twilio`, `xmpp`, `server`.
- Add `emoji>=1.7.0` to the existing `telegram` extra (its sole consumer).
- Add `redis>=5.0` to the existing `azure` extra (the O365 token store imports it).
- Make the `all` extra a true superset of every other non-`dev` extra.
- Regenerate `uv.lock` with `uv lock` in the same commit.

**NOT in scope**: any change under `notify/` (TASK-34 / TASK-35 own that);
`PROVIDER_EXTRAS` in `notify/notify.py` (TASK-34); README / CHANGES (TASK-36);
the new test files (TASK-38). Do **not** reduce the install weight of `all`, and
do **not** declare `requests` / `aiofiles` — spec §7 leaves them arriving
transitively via their own extras, deliberately.

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `pyproject.toml` | MODIFY | Slim `[project] dependencies`; add 5 extras; extend `telegram`, `azure`, `all` |
| `uv.lock` | MODIFY | Regenerate with `uv lock` — never hand-edit |

---

## Codebase Contract (Anti-Hallucination)

> Verified against `dev` @ `d72fe6e` on 2026-09-29.

### Verified current state

```toml
# pyproject.toml:35-44 — core dependencies as they stand TODAY
dependencies = [
  "aiosmtplib>=5.0",
  "python-datamodel>=0.3.12",
  "navconfig[default]>=2.2.0",
  "jinja2>=3.1.4",
  "cloudpickle>=3.1.0",
  "emoji>=1.7.0",
  "aiobotocore>=2.15.2",
  "pillow>=8.3.2",
]

# pyproject.toml:46 — the extras table opens here
[project.optional-dependencies]
```

Extras that exist today, verified by reading `pyproject.toml:46-120`:
`uvloop`, `default`, `telegram`, `push`, `google`, `azure`, `templates`, `all`, `dev`.

```toml
# pyproject.toml:55-58  telegram (gains emoji)
telegram = ["aiogram>=3.14.0", "moviepy>=2.2.1"]

# pyproject.toml:67-73  azure (gains redis) — cryptography floor is an INVARIANT
azure = ["msal>=1.32.0", "msgraph-core>=1.3.2", "azure-identity>=1.23.0",
         "msgraph-sdk>=1.22.0", "cryptography>=42.0"]

# pyproject.toml:46-48  uvloop carries an environment marker — preserve it verbatim
uvloop = ["uvloop>=0.20.0; sys_platform != 'win32'"]

# pyproject.toml:80-98  all — currently 18 entries, already free of pillow/o365
```

### Distributions imported directly, verified by AST scan (spec §6 table)

| Extra | Ships | For provider |
|---|---|---|
| `ses` (new) | `aiobotocore>=2.15.2` | `ses` |
| `slack` (new) | `slack_bolt>=1.18.0` | `slack` |
| `twilio` (new) | `twilio>=8.2.2` | `twilio` |
| `xmpp` (new) | `slixmpp>=1.10.0` | `xmpp` |
| `server` (new) | `cloudpickle>=3.1.0`, `qworker>=1.12.7`, `redis>=5.0` | `notify/server/` |

Server imports verified: `notify/server/server.py:10-12` (`redis`, `cloudpickle`),
`notify/server/client.py:5-9` (`cloudpickle`, `redis`, `qw`).

### Invariants asserted by an EXISTING test — must keep passing unmodified

`tests/test_office365_configuration.py:42-58`:
- `test_legacy_azure_packages_removed_from_extras` — for `azure` **and** `all`:
  no `pyo365`, no `office365-rest-python-client`, and no entry starting with `o365`.
- `test_cryptography_explicit_in_azure_and_all_extras` — for `azure` **and** `all`:
  some entry starts with `cryptography>=42.0` (lowercased).

### Does NOT Exist

- ~~`pillow` / `PIL` imported anywhere under `notify/`~~ — zero occurrences. It is
  dropped outright, from core **and** from every extra. Do not relocate it.
- ~~an `aiohttp` declaration in `pyproject.toml`~~ — it is undeclared today; this
  task adds the first one, in core.
- ~~a `redis` declaration in `pyproject.toml`~~ — undeclared today; this task adds it
  to `azure` and `server`.
- ~~`slack_sdk` as its own entry~~ — it arrives with `slack_bolt`; do not add it.
- ~~an existing `ses` / `slack` / `twilio` / `xmpp` / `server` extra~~ — all five are new.

---

## Implementation Notes

### Discovered gap you MUST resolve — the `all` extra is NOT a superset today

Verified by reading `pyproject.toml`: `all` currently omits `uvloop` (from the
`uvloop` extra) and `jinja2-time`, `jinja2-iso8601`, `jinja2-humanize-extension`
(from the `templates` extra). Spec **AC-G4** requires `all` to be a superset of
every non-`dev` extra, and TASK-38 will assert exactly that. So `all` must gain,
in this task:

- the five new extras' distributions: `aiobotocore`, `slack_bolt`, `twilio`,
  `slixmpp` (already present), `cloudpickle`, `qworker` (already present), `redis`
- `emoji` (moved out of core)
- the three `templates` jinja2-* packages
- `uvloop>=0.20.0; sys_platform != 'win32'` — **keep the marker verbatim**, so
  `all` stays installable on Windows

### `uv.lock` is stale in a second way — regenerating fixes both

`uv.lock:470-477` still records `aiobotocore`, `cloudpickle`, `emoji` and
`pillow` as core deps, **and** its `all` extra still lists `o365` and
`office365-rest-python-client`, which `pyproject.toml` dropped in FEAT-004.
`uv lock` resolves both. Never hand-edit the lock.

### Key Constraints

- `uv` only, inside the venv: `source .venv/bin/activate` first.
- The `aiohttp>=3.10` and `redis>=5.0` floors are proposed from this checkout
  (installed: 3.14.3 and 5.2.1). Spec §7 asks you to confirm they resolve; if
  `uv lock` cannot satisfy one, report it rather than silently widening it.
- `[tool.uv] override-dependencies = ["moviepy>=2.2.1"]` (`pyproject.toml:150-152`)
  must stay as it is.

---

## Implementation Blueprint

### Steps (in order)

1. Rewrite `[project] dependencies` — *why*: G3 is defined as the absence of those
   four packages from core, and `aiohttp` must land in the same edit or three
   providers lose their only supplier.
2. Append the five new extras next to the existing ones — *why*: TASK-34's
   `PROVIDER_EXTRAS` values must name real extras (AC-G4), and TASK-38 asserts it.
3. Extend `telegram` and `azure` — *why*: `emoji` and `redis` need a declaring
   parent once they leave core / stop arriving transitively.
4. Rebuild `all` as a true superset — *why*: AC-G4, and the gap documented above
   means this is an edit, not a no-op.
5. Run `uv lock`, then confirm the lock's `async-notify` core block matches — *why*:
   AC-G3 names the lock explicitly; editing only `pyproject.toml` leaves
   reproducible installs on the old core set.
6. Run `pytest tests/test_office365_configuration.py -v` **unmodified** — *why*:
   AC-G4 makes that file the invariant guard for this edit.

### `pyproject.toml` (MODIFY — core dependencies)

```toml
# occurrences: 1 (verified: grep -c '^dependencies = \[' pyproject.toml)
# REPLACE the whole block below `dependencies = [` (verified: pyproject.toml:35-44)
dependencies = [
  "aiosmtplib>=5.0",
  "python-datamodel>=0.3.12",
  "navconfig[default]>=2.2.0",
  "jinja2>=3.1.4",
  "aiohttp>=3.10",
]
```
**Why this shape**: exactly the spec §3 M2 target state. `pillow`, `emoji`,
`aiobotocore` and `cloudpickle` leave; `aiohttp` is promoted because `aiobotocore`
was its only core-path supplier and `dialpad`/`zoom`/`teams` import it directly
(spec §7). The remaining four are what the provider-agnostic core path genuinely
needs. Do not reorder or re-floor the four survivors.

### `pyproject.toml` (MODIFY — new extras)

```toml
# occurrences: 1 (verified: grep -c '^\[project.optional-dependencies\]' pyproject.toml)
# AFTER — insert the five new extras inside the existing
# `[project.optional-dependencies]` table (verified: pyproject.toml:46),
# alongside the existing entries and BEFORE `all`.
ses = ["aiobotocore>=2.15.2"]
slack = ["slack_bolt>=1.18.0"]
twilio = ["twilio>=8.2.2"]
xmpp = ["slixmpp>=1.10.0"]
server = [
  "cloudpickle>=3.1.0",
  "qworker>=1.12.7",
  "redis>=5.0",
]
```
**Why**: one extra per provider that needs a third-party SDK (G4), plus `server`
so `notify/__main__.py` and `notify/server/` keep a declaring parent after
`cloudpickle` leaves core. Extra **names** are the contract TASK-34's
`PROVIDER_EXTRAS` cites — do not rename them.

### `pyproject.toml` (MODIFY — telegram and azure)

```toml
# occurrences: 1 (verified: grep -c '^telegram = \[' pyproject.toml)
# REPLACE (verified: pyproject.toml:55-58)
telegram = [
  "aiogram>=3.14.0",
  "moviepy>=2.2.1",
  "emoji>=1.7.0",
]

# occurrences: 1 (verified: grep -c '^azure = \[' pyproject.toml)
# AFTER — append one entry inside the existing `azure` list, below
# `"cryptography>=42.0",` (verified: pyproject.toml:72)
  "redis>=5.0",
```
**Why**: telegram is `emoji`'s sole consumer (spec §6 table), and the O365 token
store imports `redis` directly. `cryptography>=42.0` must stay in `azure`
verbatim — `tests/test_office365_configuration.py:53-58` asserts it.

### `pyproject.toml` (MODIFY — the `all` superset)

```toml
# occurrences: 1 (verified: grep -c '^all = \[' pyproject.toml)
# REPLACE the whole `all` list (verified: pyproject.toml:80-98).
# Keep every entry it already has, then add the ones marked below.
all = [
  # ... every existing entry, unchanged ...
  # FILL IN: carry over all 18 current entries verbatim, then add the
  # missing ones so `all` is a true superset — bounded by AC-G4 and by
  # TASK-38's test_all_extra_is_a_superset:
  #   emoji>=1.7.0            (left core)
  #   cloudpickle>=3.1.0      (left core, now in `server`)
  #   redis>=5.0              (new in `azure` + `server`)
  #   jinja2-time / jinja2-iso8601 / jinja2-humanize-extension  (from `templates`)
  #   uvloop>=0.20.0; sys_platform != 'win32'   (from `uvloop`, marker VERBATIM)
  # Do NOT add pillow. Do NOT add o365 / office365-rest-python-client /
  # pyo365 — tests/test_office365_configuration.py:42-51 forbids them.
]
```
**Why**: `all` is the only extra whose contract is "everything", and AC-G4 plus
TASK-38 turn that into an assertion. `aiobotocore`, `slack_bolt`, `twilio`,
`slixmpp` and `qworker` are already listed — verify rather than duplicate. The
`uvloop` marker must survive the copy or `all` stops installing on Windows.

### `uv.lock` (MODIFY — regenerate)

```bash
source .venv/bin/activate
uv lock
# Verify the regenerated core block — it must list exactly the five core deps:
sed -n '/^name = "async-notify"/,/^\[package.optional-dependencies\]/p' uv.lock
```
**Why**: AC-G3 requires the lock's `async-notify` core dependency list to match
`pyproject.toml`. Regeneration also clears the stale `o365` /
`office365-rest-python-client` entries still sitting in the lock's `all` extra.

### FILL IN checklist

- [ ] `pyproject.toml::all` — carry the 18 existing entries over verbatim and add the
      7 listed additions; bounded by AC-G4 and TASK-38's superset test.
- [ ] `aiohttp>=3.10` / `redis>=5.0` floors — confirm `uv lock` resolves them; if not,
      report the conflict instead of widening the floor (spec §7).

---

## Acceptance Criteria

- [ ] `[project] dependencies` contains none of `pillow`, `emoji`, `aiobotocore`,
      `cloudpickle`, and does contain `aiohttp>=3.10`. *(AC-G3)*
- [ ] Extras `ses`, `slack`, `twilio`, `xmpp`, `server` all exist with the contents above. *(AC-G4)*
- [ ] `telegram` contains `emoji>=1.7.0`; `azure` contains `redis>=5.0`.
- [ ] `all` is a superset of every non-`dev` extra, including `uvloop` and `templates`. *(AC-G4)*
- [ ] `azure` and `all` still contain `cryptography>=42.0` and still exclude
      `pyo365` / `o365` / `Office365-REST-Python-Client`. *(AC-G4)*
- [ ] `uv.lock` regenerated; its `async-notify` core block matches `pyproject.toml`. *(AC-G3)*
- [ ] `PYTHONPATH=. pytest tests/test_office365_configuration.py -v` passes with that
      file **unmodified**.
- [ ] `pip install -e .` (or `uv sync`) still resolves in a clean environment.

---

## Test Specification

No new test file in this task — TASK-38 writes `tests/test_dependency_manifest.py`
against this manifest. The guard for *this* task is the existing suite:

```bash
source .venv/bin/activate
PYTHONPATH=. pytest tests/test_office365_configuration.py -v   # must pass UNMODIFIED
python - <<'PY'
import tomllib
d = tomllib.load(open("pyproject.toml","rb"))["project"]
core = " ".join(d["dependencies"])
assert not any(p in core for p in ("pillow", "emoji", "aiobotocore", "cloudpickle")), core
assert "aiohttp" in core, core
ex = d["optional-dependencies"]
for name in ("ses", "slack", "twilio", "xmpp", "server"):
    assert name in ex, name
allset = {e.split(">=")[0].split(";")[0].strip().lower().replace("_", "-") for e in ex["all"]}
for name, deps in ex.items():
    if name in ("all", "dev"):
        continue
    for dep in deps:
        d0 = dep.split(">=")[0].split(";")[0].strip().lower().replace("_", "-")
        assert d0 in allset, f"{name}:{d0} missing from all"
print("manifest OK")
PY
```

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** §3 Module 2, §5 (G3/G4) and §7 for full context.
2. **Check dependencies** — none; this task runs first.
3. **Verify the Codebase Contract** — re-read `pyproject.toml` before editing;
   confirm the line ranges above and the current contents of `all`.
4. Update this feature's index entry to `in-progress`.
5. **Implement** from the blueprint; resolve every `FILL IN`.
6. **Verify** every acceptance criterion, including the `uv lock` regeneration.
7. **Move this file** to `sdd/tasks/completed/`.
8. **Update** `sdd/tasks/index/lazy-import-providers.json` → `"done"`.
9. **Fill in the Completion Note** below.

---

## Completion Note

*(Agent fills this in when done)*

**Completed by**: <session or agent ID>
**Date**: YYYY-MM-DD
**Notes**:

**Deviations from spec**: none | describe if any
