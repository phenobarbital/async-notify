# TASK-38: Lock the dependency manifest and README ↔ manifest parity

**Feature**: FEAT-005 — Actionable optional-dependency diagnostics and a slim core install
**Spec**: `sdd/specs/lazy-import-providers.spec.md`
**Status**: pending
**Priority**: medium
**Estimated effort**: S (< 2h)
**Depends-on**: TASK-33, TASK-36
**Assigned-to**: unassigned

---

## Context

Implements the **M2/M4 slice of spec §3 Module 5**, locking goals **G3**, **G4**
and the parity half of **G5**.

TASK-33's manifest is the kind of change that silently rots: a future contributor
adds a provider extra and forgets `all`, or adds an entry to `PROVIDER_EXTRAS`
naming an extra that does not exist, and nothing complains until a user's install
is wrong. These tests are the drift guard the user explicitly asked for in spec §8
("a stronger bidirectional drift test was offered and declined" — so this is the
weaker, agreed form: every `PROVIDER_EXTRAS` **value** must name a real extra).

Depends on TASK-36 as well as TASK-33 because `test_readme_matrix_matches_manifest`
reads `README.md`.

---

## Scope

- Create `tests/test_dependency_manifest.py` with the five manifest/doc tests named
  in spec §4.

**NOT in scope**: `tests/test_provider_dependencies.py` (TASK-37),
`tests/test_startup_imports.py` (TASK-39), any edit to `pyproject.toml`,
`README.md` or `CHANGES.rst` (TASK-33 / TASK-36 own those — if a test fails, fix
the manifest or the docs, not the test). `tests/test_office365_configuration.py`
must stay **unmodified**: this task *re-asserts* its invariants, it does not move
or rewrite them.

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `tests/test_dependency_manifest.py` | CREATE | Manifest invariants + README parity |

---

## Codebase Contract (Anti-Hallucination)

> Verified against `dev` @ `d72fe6e` on 2026-09-29. The manifest shape this task
> asserts is TASK-33's **output** — read the landed `pyproject.toml`, not this file.

### Verified Imports

```python
import tomllib                                          # stdlib (Python >= 3.11)
from pathlib import Path
from notify.notify import PROVIDER_EXTRAS               # (TASK-34) — does not exist on dev
```

### Pattern to follow — an existing test already does this

```python
# tests/test_office365_configuration.py:1-15  — copy this shape verbatim
from pathlib import Path
import tomllib

PYPROJECT_PATH = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _load_pyproject() -> dict:
    with open(PYPROJECT_PATH, "rb") as fh:
        return tomllib.load(fh)
```

### Invariants already asserted elsewhere — re-assert, do not relocate

```python
# tests/test_office365_configuration.py:42-51
def test_legacy_azure_packages_removed_from_extras():
    # for "azure" and "all": no pyo365, no office365-rest-python-client,
    # and no entry starting with "o365"

# tests/test_office365_configuration.py:53-58
def test_cryptography_explicit_in_azure_and_all_extras():
    # for "azure" and "all": some entry startswith "cryptography>=42.0"
```

### Manifest facts this task asserts (TASK-33's target state)

- Core contains **none** of `pillow`, `emoji`, `aiobotocore`, `cloudpickle`.
- Core **does** contain `aiohttp`.
- Extras `ses`, `slack`, `twilio`, `xmpp`, `server` all exist.
- `all` is a superset of every non-`dev` extra.
- `PROVIDER_EXTRAS` values ⊆ `[project.optional-dependencies]` keys.

### Requirement-string parsing — the trap

Extras hold PEP 508 requirement strings, not bare names. All of these appear in
this manifest and must normalise to a comparable name:

| String | Name |
|---|---|
| `"aiobotocore>=2.15.2"` | `aiobotocore` |
| `"uvloop>=0.20.0; sys_platform != 'win32'"` | `uvloop` |
| `"navconfig[default]>=2.2.0"` | `navconfig` |
| `"slack_bolt>=1.18.0"` vs `"slack-bolt"` | `slack-bolt` (PEP 503: `_` ≡ `-`) |
| `"onesignal-sdk>=2.0.0"` | `onesignal-sdk` |

Normalise with PEP 503: lowercase, and collapse runs of `-`, `_`, `.` to a single
`-`. Strip the environment marker (everything after `;`) and the extras bracket
**before** splitting on the version specifier.

### Does NOT Exist

- ~~`packaging` as a guaranteed dependency~~ — it is not in `[project] dependencies`
  and not in `dev`. Do **not** `import packaging.requirements`; parse with `re`
  and stdlib only, or the test fails on a clean install.
- ~~a `tests/conftest.py`~~ — there is none.
- ~~`pytest.ini` markers beyond `integration` / `live` / `real_llm`~~ — only those
  three are declared. This file needs none of them.
- ~~a bidirectional `PROVIDER_EXTRAS` drift test~~ — spec §8 records that it was
  **offered and declined**. Assert values-name-real-extras only; do **not** also
  assert that every extra has a `PROVIDER_EXTRAS` entry (`all`, `server`, `uvloop`,
  `templates`, `default` legitimately have none).

---

## Implementation Notes

### The `all` superset test will fail unless TASK-33 did its job

Verified on `dev`: `all` currently omits `uvloop` and the three `templates`
jinja2-* packages, so this assertion is **not** vacuous — it is exactly the gap
TASK-33 was told to close. If it fails when you run it, that is a real finding:
fix `pyproject.toml`, and say so in your Completion Note.

### Key Constraints

- Pure file parsing — no network, no install, no subprocess. Fast enough to run
  on every commit.
- Import `PROVIDER_EXTRAS` from `notify.notify`. That import pulls in the package,
  so this file is **not** suitable for startup-purity assertions — those belong to
  TASK-39, in a subprocess.
- Exclude `dev` from the superset check (it holds tooling, not runtime deps).
  Decide explicitly whether `uvloop` and `templates` participate — spec AC-G4 says
  "every other non-`dev` extra", so they do.
- Google-style docstrings, `black --line-length 120`.

---

## Implementation Blueprint

### Steps (in order)

1. Copy the `PYPROJECT_PATH` / `_load_pyproject()` preamble from
   `tests/test_office365_configuration.py` — *why*: one parsing idiom in the repo,
   and it is already proven against this file.
2. Write the normaliser — *why*: every remaining test compares distribution names,
   and a naive `split(">=")` mis-handles the `uvloop` marker and `navconfig[default]`.
3. Write the four manifest tests — *why*: AC-G3 and AC-G4.
4. Write the README parity test — *why*: AC-G5's machine-checkable half.

### `tests/test_dependency_manifest.py` (CREATE)

```python
"""Dependency-manifest and documentation-parity tests (FEAT-005, M2/M4).

Locks spec §5 goals G3 (slim core), G4 (an extra per provider SDK) and the
README-parity half of G5. Pure file parsing — no network, no install.
"""
import re
import tomllib
from pathlib import Path

from notify.notify import PROVIDER_EXTRAS

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
README_PATH = REPO_ROOT / "README.md"

#: Packages that must not be installed by the bare `async-notify` distribution.
BANNED_FROM_CORE = ("pillow", "emoji", "aiobotocore", "cloudpickle")


def _load_pyproject() -> dict:
    """Parse ``pyproject.toml`` — same idiom as tests/test_office365_configuration.py."""
    with open(PYPROJECT_PATH, "rb") as fh:
        return tomllib.load(fh)


def _dist_name(requirement: str) -> str:
    """Normalise a PEP 508 requirement string to its PEP 503 distribution name.

    Handles environment markers (``; sys_platform != 'win32'``), extras
    brackets (``navconfig[default]``) and every version specifier form.

    Args:
        requirement: A raw entry from ``dependencies`` or an extra.

    Returns:
        The lowercased, dash-normalised distribution name.
    """
    # FILL IN: strip everything from ";" onwards, then the "[...]" extras
    # bracket, then split on the first of < > = ! ~ ; finally lowercase and
    # re.sub(r"[-_.]+", "-", name).strip(). Bounded by the parsing table in the
    # Codebase Contract — all five listed forms must normalise correctly.
    raise NotImplementedError


def test_core_dependencies_are_minimal():
    """AC-G3 — the four demoted packages are gone from core; aiohttp is in."""
    core = {_dist_name(d) for d in _load_pyproject()["project"]["dependencies"]}
    for banned in BANNED_FROM_CORE:
        assert _dist_name(banned) not in core, f"{banned} must not be a core dependency"
    assert "aiohttp" in core, "aiohttp must be promoted into core"


def test_provider_extras_names_exist_in_pyproject():
    """AC-G4 — every PROVIDER_EXTRAS value names a real extra."""
    extras = set(_load_pyproject()["project"]["optional-dependencies"])
    unknown = {v for v in PROVIDER_EXTRAS.values() if v not in extras}
    assert not unknown, f"PROVIDER_EXTRAS names non-existent extras: {sorted(unknown)}"


def test_all_extra_is_a_superset():
    """AC-G4 — `all` contains every distribution from every non-dev extra."""
    extras = _load_pyproject()["project"]["optional-dependencies"]
    # FILL IN: build the normalised name set of extras["all"], then for every
    # extra except "all" and "dev", assert each of its normalised names is in
    # that set. Report the offending extra:name pair in the assertion message.
    # Bounded by AC-G4 ("superset of every other non-`dev` extra") — uvloop and
    # templates are included, deliberately.
    raise NotImplementedError


def test_azure_invariants_preserved():
    """AC-G4 — re-assert tests/test_office365_configuration.py:42-58.

    That file must keep passing unmodified; this is a second, local guard so a
    manifest edit fails here too, next to the rest of the manifest contract.
    """
    extras = _load_pyproject()["project"]["optional-dependencies"]
    for name in ("azure", "all"):
        deps = extras[name]
        assert any(d.lower().startswith("cryptography>=42.0") for d in deps), name
        joined = " ".join(deps).lower()
        assert "pyo365" not in joined, name
        assert "office365-rest-python-client" not in joined, name
        assert not any(d.lower().startswith("o365") for d in deps), name


def test_readme_matrix_matches_manifest():
    """AC-G5 — every non-dev extra is documented, and vice versa."""
    extras = set(_load_pyproject()["project"]["optional-dependencies"]) - {"dev"}
    readme = README_PATH.read_text(encoding="utf-8")
    # FILL IN: assert every extra in `extras` appears in the README, and that
    # the README mentions no `async-notify[<name>]` whose <name> is not an extra.
    # Bounded by AC-G5 ("Every extra in pyproject.toml appears in the README
    # table and vice versa"). Pick ONE recognisable citation form and state it
    # in the assertion message, so TASK-36's table has an unambiguous target —
    # `async-notify[<extra>]` is the form TASK-36's blueprint uses.
    raise NotImplementedError
```
**Why this shape**: spec §4's M2/M4 rows one-for-one. `_dist_name` is factored out
because four of the five tests compare names and the manifest genuinely contains a
marker, an extras bracket and both `_`/`-` spellings — a per-test `split(">=")`
would pass while comparing the wrong strings. `test_azure_invariants_preserved`
duplicates an existing test on purpose: AC-G4 names that file as the invariant
guard, and a second local copy means a manifest edit fails in the file a
contributor is already looking at. Assertion messages name the offending entry —
a bare `assert False` on a 25-entry extra is not actionable.

### FILL IN checklist

- [ ] `_dist_name` — handle marker, extras bracket, all specifier forms, PEP 503
      normalisation; bounded by the Codebase Contract's parsing table.
- [ ] `test_all_extra_is_a_superset` — exclude only `all` and `dev`; name the
      offending pair; AC-G4.
- [ ] `test_readme_matrix_matches_manifest` — bidirectional, one citation form;
      AC-G5.

---

## Acceptance Criteria

- [ ] All five tests exist and pass:
      `PYTHONPATH=. pytest tests/test_dependency_manifest.py -v`
- [ ] `_dist_name` normalises every form in the Codebase Contract table — assert
      this directly (a small parametrised test, or inline asserts).
- [ ] No `packaging` import; stdlib only.
- [ ] `tests/test_office365_configuration.py` untouched and still passing.
- [ ] `PYTHONPATH=. pytest tests/ -v` passes.
- [ ] `black --line-length 120`, `flake8`, `pylint` clean on the new file.

---

## Test Specification

Spec §4's M2/M4 rows, reproduced:

| Test | Asserts |
|---|---|
| `test_provider_extras_names_exist_in_pyproject` | Every `PROVIDER_EXTRAS` value is a key of `[project.optional-dependencies]` |
| `test_core_dependencies_are_minimal` | Core has none of `pillow`, `emoji`, `aiobotocore`, `cloudpickle` |
| `test_all_extra_is_a_superset` | Every distribution in any non-`dev` extra also appears in `all` |
| `test_azure_invariants_preserved` | `azure`/`all` keep `cryptography>=42.0`, exclude `pyo365`/`o365`/`Office365-REST-Python-Client` |
| `test_readme_matrix_matches_manifest` | Every extra appears in the README table and vice versa |

Run:
```bash
source .venv/bin/activate
python setup.py build_ext --inplace
PYTHONPATH=. pytest tests/test_dependency_manifest.py tests/test_office365_configuration.py -v
```

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** §3 Modules 2 and 4, §4, and §5 (G3/G4/G5).
2. **Check dependencies** — TASK-33 **and** TASK-36 must be in
   `sdd/tasks/completed/`; TASK-34 must have landed too, for `PROVIDER_EXTRAS`.
3. **Verify the Codebase Contract** — read the **landed** `pyproject.toml` and
   `README.md`; take the extra names from them.
4. Update this feature's index entry to `in-progress`.
5. **Implement** from the blueprint; resolve every `FILL IN`. If a test fails, fix
   the manifest or the docs — never weaken the assertion.
6. **Verify** every acceptance criterion.
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
