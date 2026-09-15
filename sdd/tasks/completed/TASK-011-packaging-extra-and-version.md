# TASK-011: Declare the `templates` optional extra and bump to 1.6.0

**Feature**: FEAT-002 — TemplateParser refactor (homologation with ai-parrot TemplateEngine)
**Spec**: `sdd/specs/templateparser-refactor.spec.md`
**Status**: pending
**Priority**: medium
**Estimated effort**: S (< 2h)
**Depends-on**: none
**Assigned-to**: unassigned

---

## Context

Implements **Module 5** of the spec (§3). TASK-007 loads three third-party
Jinja2 extensions tolerantly; this task makes them *installable* by declaring a
`templates` optional-dependency group, and bumps the package version to the
target release.

This task touches only `pyproject.toml` and `notify/version.py` — no code
shares a file with any other task in FEAT-002, so it is safe to run in parallel.

**An open question from the spec must be resolved here** (§9): the exact PyPI
distribution names and version floors for the three extensions are
**unverified**. `jinja2_time`, `jinja2_iso8601` and `jinja2_humanize_extension`
are the *import* names used by ai-parrot's `JinjaConfig.extensions`
(`engine.py:29-37`), but ai-parrot declares none of them in any `pyproject.toml`
— confirmed by exhaustive grep across that repo. Do not guess: check PyPI.

---

## Scope

- Verify on PyPI the distribution name and a sensible version floor for each of:
  - `jinja2_time.TimeExtension`
  - `jinja2_iso8601.ISO8601Extension`
  - `jinja2_humanize_extension.HumanizeExtension`
- Add a `[project.optional-dependencies]` group named `templates` to
  `pyproject.toml` listing the verified distributions.
- If a distribution cannot be found on PyPI or is clearly unmaintained, **omit
  it** from the extra, remove its dotted path from
  `JinjaConfig.optional_extensions`, and record the decision in the Completion
  Note. Do not invent a package name.
- Bump `notify/version.py` `__version__` from `1.5.7` to `1.6.0`.
- Check whether any other file carries the version (e.g. `pyproject.toml`
  `[project] version`, docs, `setup.py`) and keep them consistent.

**NOT in scope**: any change to `notify/templates.py` (TASK-007, 008, 009) or
`notify/notify.py` (TASK-010); tests (TASK-012, TASK-013); release notes or
changelog authoring.

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `pyproject.toml` | MODIFY | Add `[project.optional-dependencies] templates` |
| `notify/version.py` | MODIFY | `__version__` → `1.6.0` |

---

## Codebase Contract (Anti-Hallucination)

### Verified References

```toml
# pyproject.toml:41 — jinja2 is ALREADY a hard dependency, no bump needed.
# ChoiceLoader, DictLoader, FileSystemBytecodeCache and select_autoescape
# all ship in jinja2 3.1.
  "jinja2>=3.1.4",
```

```python
# notify/version.py:8
__version__ = "1.5.7"
```

```python
# Dotted extension paths consumed by JinjaConfig.optional_extensions (TASK-007)
"jinja2_time.TimeExtension"
"jinja2_iso8601.ISO8601Extension"
"jinja2_humanize_extension.HumanizeExtension"
```

### Existing pyproject structure to match

```toml
# pyproject.toml — dev dependencies live around lines 106-115 as a plain list
  "pytest>=8.0.0",
  "pytest-asyncio>=0.24.0",
  ...

# [project.scripts] is at line 117-118
[project.scripts]
notify = "notify.__main__:main"

# [tool.pytest.ini_options] is at line 153
# [tool.mypy] is at line 160
```

Read `pyproject.toml` in full before editing — place the new
`[project.optional-dependencies]` table in the `[project]` section, not inside
a `[tool.*]` table.

### Does NOT Exist

- ~~`[project.optional-dependencies]` in `pyproject.toml`~~ — verify with
  `grep -n 'optional-dependencies' pyproject.toml`; if the table already exists,
  ADD the `templates` key rather than creating a second table (duplicate tables
  are a TOML parse error).
- ~~`jinja2-time` / `jinja2-iso8601` / `jinja2-humanize-extension` as verified
  PyPI distributions~~ — these are plausible *guesses* derived from the import
  names. **They are unverified.** Confirm each on PyPI before writing it down.
- ~~Any declaration of these three packages in ai-parrot~~ — exhaustive grep
  across `../ai-parrot` for `jinja2.time|jinja2_time|jinja2-time|iso8601|humanize`
  in `*.toml`, `*.txt`, `*.cfg` returned zero hits. There is no upstream
  reference to copy.
- ~~A `CHANGELOG.md` in this repo~~ — verify with `ls CHANGELOG*` before trying
  to update one.

---

## Implementation Notes

### Pattern to Follow

```toml
[project.optional-dependencies]
templates = [
    "<verified-dist-name>>=<verified-floor>",
    # one line per extension that actually resolves on PyPI
]
```

Verification command (network required):

```bash
.venv/bin/python -m pip index versions <candidate-name>
# or
.venv/bin/python -m pip download --no-deps -d /tmp/probe <candidate-name>
```

### Key Constraints

- **The extra must be genuinely optional.** TASK-007 loads each extension in its
  own `try/except`; nothing here may make them hard requirements. A minimal
  `pip install async-notify` must keep working.
- **Do not guess a package name.** An unresolvable name in an extra turns
  `pip install async-notify[templates]` into a hard failure — worse than
  omitting the extension.
- Keep the version bump to `notify/version.py` only unless another file
  genuinely duplicates the version; check first.
- If `pyproject.toml` derives `version` dynamically from `notify/version.py`,
  do NOT add a static `version` field.

### References in Codebase

- `pyproject.toml:41` — the existing `jinja2` pin.
- `notify/version.py:8` — the version string.
- Recent commit `ccb20eb` ("build: drop setuptools-scm to fix manylinux wheel
  build") and `a8b99bc` ("build: scope wheel contents to notify/* only") —
  read these before touching packaging metadata; the build config was recently
  reworked and is sensitive.

---

## Acceptance Criteria

- [ ] Every distribution listed in the `templates` extra resolves on PyPI (verified, not assumed)
- [ ] Any extension that could NOT be verified is omitted from the extra AND removed from `JinjaConfig.optional_extensions`, with the reason recorded in the Completion Note
- [ ] `[project.optional-dependencies]` appears exactly once in `pyproject.toml`
- [ ] `pyproject.toml` parses: `.venv/bin/python -c "import tomllib,pathlib; tomllib.loads(pathlib.Path('pyproject.toml').read_text())"`
- [ ] `notify/version.py` reports `1.6.0`
- [ ] No other file still reports `1.5.7`: `grep -rn '1\.5\.7' --include='*.py' --include='*.toml' .` is clean
- [ ] A build still succeeds: `.venv/bin/python -m build --wheel` (or the project's documented build command)
- [ ] `jinja2` remains a hard dependency at `>=3.1.4`; no version bump

---

## Test Specification

No unit tests. Verification is by inspection and the commands above:

```bash
.venv/bin/python -c "from notify.version import __version__; print(__version__)"
# → 1.6.0

.venv/bin/python -c "import tomllib,pathlib; d=tomllib.loads(pathlib.Path('pyproject.toml').read_text()); print(d['project'].get('optional-dependencies'))"
# → {'templates': [...]}
```

---

## Agent Instructions

1. **Read the spec** — §3 Module 5, §7 "External Dependencies", §9 (the open
   question this task resolves).
2. **Check dependencies** — none. This task may run in parallel with TASK-008,
   TASK-009 and TASK-010.
3. **Verify the Codebase Contract** — read `pyproject.toml` in full and
   `notify/version.py` before editing.
4. **Update status** in `sdd/tasks/index/templateparser-refactor.json` → `in-progress`.
5. **Resolve the PyPI question first**, then edit. If you cannot reach the
   network, STOP and report — do not write unverified package names.
6. **Verify** every acceptance criterion.
7. **Move this file** to `sdd/tasks/completed/TASK-011-packaging-extra-and-version.md`.
8. **Update index** → `done`.
9. **Fill in the Completion Note** with the resolved package names and floors,
   and any extension you dropped.

Use `.venv/bin/python` directly — `.venv/bin/activate` is stale.

---

## Completion Note

**Completed by**: sdd-worker (Claude)
**Date**: 2026-08-06
**Notes**: Verified all three distributions on PyPI via
`pip index versions` and `pip download --no-deps` (network available),
then inspected each wheel's contents to confirm the import module name
and extension class match `JinjaConfig.optional_extensions` exactly:
`jinja2_time.TimeExtension`, `jinja2_iso8601.ISO8601Extension`,
`jinja2_humanize_extension.HumanizeExtension`. `[project.optional-
dependencies]` already existed in `pyproject.toml`; added the `templates`
key to it rather than creating a second table. Bumped
`notify/version.py::__version__` to `1.6.0`; `pyproject.toml` derives its
version dynamically from `notify.version.__version__`
(`[tool.setuptools.dynamic]`), so no static `version` field was touched.
The only remaining `1.5.7` string in the tree is a historical reference
inside a `notify/templates.py` docstring ("reproduces async-notify's
behaviour as of 1.5.7") — intentionally left as-is; it documents a past
version's behaviour, not the current release. `jinja2>=3.1.4` left
unchanged. Verified: TOML parses, `templates` extra readable via
`tomllib`, `python -m build --wheel` succeeds and produces
`async_notify-1.6.0-*.whl`. Full `pytest tests/ -v`: 59 passed, 2 failed +
3 errors, identical to the pre-existing `dev` baseline.

**Resolved package names / floors**:
- `jinja2-time>=0.2.0` (latest on PyPI: 0.2.0)
- `jinja2-iso8601>=1.0.0` (latest on PyPI: 1.0.0)
- `jinja2-humanize-extension>=0.4.0` (latest on PyPI: 0.4.0)

**Extensions dropped (and why)**: none — all three resolved cleanly on
PyPI with import names matching `JinjaConfig.optional_extensions`.

**Deviations from spec**: none
