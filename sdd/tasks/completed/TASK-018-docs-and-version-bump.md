# TASK-018: Document inline template source and bump version to 1.6.0

**Feature**: FEAT-003 — Inline Jinja2 template source for `send()`
**Spec**: `sdd/specs/jinja-string-notify.spec.md`
**Status**: pending
**Priority**: medium
**Estimated effort**: S (< 2h)
**Depends-on**: TASK-014, TASK-015, TASK-016
**Assigned-to**: unassigned

---

## Context

FEAT-003 changes the meaning of an existing public keyword: `send(template=...)`
now accepts either a filename or raw Jinja2 source. That is exactly the kind of
change that must be documented rather than discovered, for three reasons:

1. **The heuristic has a documented hole** (spec §7 R1). A body of pure literal
   text with no Jinja markup and no newline is indistinguishable from a
   filename and will raise `FileNotFoundError`. Users need to know
   `template_is_source=True` exists before they hit it.
2. **There is a real security consequence** (spec §7 R10). `autoescape` is
   `False` and stays `False`, so compiling caller-supplied source executes
   arbitrary Jinja2 and emits unescaped output. This is an SSTI surface and must
   be stated next to the usage example, not buried.
3. **The cache is observable** — `string_cache_size` and `cache=False` are knobs
   users may need for per-tenant template workloads.

Implements spec §3 Module 5.

---

## Scope

- Document in `docs/api.rst` and/or `docs/providers.rst` (pick the file that
  already documents `send()`; verify before writing):
  - `template=` now accepts a filename **or** Jinja2 source text.
  - The detection rules: `{{`, `{%`, `{#`, or a line break ⇒ source; anything
    else ⇒ filename.
  - `template_is_source=` (`None` auto / `True` force source / `False` force
    filename) and the §7 R1 case it exists for.
  - `TemplateParser.from_string(source, *, cache=True)` and
    `clear_string_cache()`.
  - The `string_cache_size` constructor kwarg and the default of 128.
  - The widened `Message.template: Union[Path, str]`.
  - **The security note** from spec §7 R10, adjacent to the usage example.
- Add a usage section to `README.md` with the three call shapes from spec §2
  ("New Public Interfaces" → caller-facing usage).
- Bump `__version__` in `notify/version.py` from `"1.5.7"` to `"1.6.0"`.

**NOT in scope**:
- Any change under `notify/` other than the single `__version__` line in
  `notify/version.py`.
- Changing `notify/version.py`'s `__copyright__`, `__author__`, or any other field.
- Writing a CHANGELOG (this repo has none — verify before creating one; if you
  believe one is warranted, note it in the Completion Note rather than adding it).
- Documenting FEAT-002 features (`JinjaConfig`, `render_string`,
  `add_templates`, multi-directory loaders). They are a different feature and
  may not be merged yet.
- Documenting OneSignal template support — it has none (spec §7 R7).

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `docs/api.rst` | MODIFY | `TemplateParser.from_string` / `clear_string_cache` / `string_cache_size` reference |
| `docs/providers.rst` | MODIFY | The overloaded `template=`, detection rules, `template_is_source=`, security note |
| `README.md` | MODIFY | Usage section with the three call shapes |
| `notify/version.py` | MODIFY | `__version__ = "1.6.0"` |

> **Verify the doc file split first.** `docs/` contains `api.rst`,
> `providers.rst`, `models.rst`, `architecture.rst`, `server.rst`,
> `examples.rst`, `index.rst`. Read them and put each piece where it belongs
> rather than following this table blindly.

---

## Codebase Contract (Anti-Hallucination)

> **CRITICAL**: This section contains VERIFIED code references from the actual codebase.
> **DO NOT** invent, guess, or assume any import, attribute, or method not listed here.

Verified 2026-08-06 against `dev@f42d302`.

### Existing Signatures to Document

```python
# notify/templates.py — after TASK-014
def is_template_source(value: str) -> bool: ...
JINJA_MARKERS: tuple[str, ...] = ("{{", "{%", "{#")
DEFAULT_STRING_CACHE_SIZE: int = 128

class TemplateParser:
    def __init__(self, directory: Path, filters: Optional[list] = None,
                 *, string_cache_size: int = DEFAULT_STRING_CACHE_SIZE, **kwargs): ...
    def from_string(self, source: str, *, cache: bool = True) -> Template: ...
    def clear_string_cache(self) -> None: ...


# notify/providers/base.py — after TASK-015
class ProviderBase(ABC):
    async def _prepare_(self, recipient=None, message=None,
                        template: Optional[str] = None,
                        template_is_source: Optional[bool] = None, **kwargs): ...
    async def send(self, recipient: list[Actor] = None,
                   message: Union[str, Any] = None,
                   subject: str = None, **kwargs): ...          # line 242


# notify/models.py — after TASK-016
class Message(BaseModel):
    template: Union[Path, str]                                  # line 93


# notify/version.py — the file to bump
__title__ = "async-notify"
__version__ = "1.5.7"          # ← change this line ONLY
__url__ = "https://github.com/phenobarbital/async-notify"
```

### Canonical usage examples (from spec §2 — use these verbatim)

```python
# raw source — new in 1.6.0
await Notify("smtp").send(
    recipient=[actor],
    subject="Welcome",
    template="<p>Hola {{ recipient.account.address }} — {{ message }}</p>",
    message="…",
)

# filename — unchanged from 1.5.7
await Notify("smtp").send(recipient=[actor], template="welcome.html")

# forced, for a body with no Jinja markup
await Notify("telegram").send(
    recipient=[chat], template="Hello world", template_is_source=True,
)
```

### Template variables available to a string template

`_render_` builds `self._templateargs` (`notify/providers/base.py:177-183`) as:

```python
{"recipient": to, "username": to, "message": message, "subject": subject, **kwargs}
```

So document `{{ recipient }}`, `{{ username }}`, `{{ message }}`, `{{ subject }}`
plus arbitrary extra kwargs. **Do NOT document `{{ content }}` as generally
available** — only `mail.py:145-151` and `ses.py:97-103` add it, the base class
does not.

### Does NOT Exist

- ~~`CHANGELOG.md`~~ / ~~`HISTORY.rst`~~ — verify with `ls`; this repo appears to have neither. Do not create one under this task.
- ~~`docs/templates.rst`~~ — verify before referencing. `docs/` holds `api.rst`, `providers.rst`, `models.rst`, `architecture.rst`, `server.rst`, `examples.rst`, `index.rst`, plus Sphinx machinery (`conf.py`, `Makefile`, `make.bat`, `requirements.txt`).
- ~~`template_string=`~~ — this keyword does **not** exist and must never appear in the docs. The API is the overloaded `template=` (spec §1 Non-Goals).
- ~~`TemplateParser.render_string()`~~ — FEAT-002, not this feature. Do not document it here even if FEAT-002 has merged.
- ~~Template support in OneSignal~~ — `Onesignal.send()` (`notify/providers/onesignal/onesignal.py:93`) never calls `_prepare_`. Do not list it among providers supporting templates.
- ~~`autoescape=True`~~ — it is `False` and stays `False`. Do not document escaping that does not happen.

---

## Implementation Notes

### The security note (required, spec §7 R10)

Place this immediately adjacent to the inline-source usage example, not in a
footnote:

> **Security — template source is executable.** `autoescape` is disabled, so a
> template compiled from a string executes arbitrary Jinja2 (attribute
> traversal, loops, registered globals and filters) and emits **unescaped**
> output. Template *source* must come from trusted operators — configuration,
> or database rows written by staff. Never build it from end-user input.
> End-user data belongs in the **parameters**, which are only ever substituted
> as values:
>
> ```python
> # SAFE — user data is a parameter
> await notify.send(recipient=[actor], template=body_from_db, name=user_input)
>
> # UNSAFE — user data becomes template code
> await notify.send(recipient=[actor], template=f"<p>Hi {user_input}</p>")
> ```

### The R1 caveat (required)

> A template body that contains no Jinja2 markup and no line break — for example
> `"Hello world"` — cannot be told apart from a filename and will be looked up
> on disk, raising `FileNotFoundError`. Pass `template_is_source=True` for that
> case.

### Key Constraints

- Match the existing `.rst` conventions in `docs/` (directive style, heading
  underline characters, code-block syntax). Read a neighbouring file first.
- Do not restructure or reformat existing documentation sections.
- **`notify/version.py`: change the `__version__` line and nothing else.**
- Verify every code example you write actually runs against the implemented API
  — these docs are the first thing a user copies.

### Merge-conflict warning

FEAT-002 (`sdd/specs/templateparser-refactor.spec.md`, TASK-011) **also bumps
`notify/version.py` to `1.6.0`**. Expect a trivial both-changed conflict on
whichever branch merges second; resolve to the single line
`__version__ = "1.6.0"`. Do not "fix" it by choosing a different version number.

### References in Codebase

- `docs/providers.rst`, `docs/api.rst` — existing style to match.
- `README.md` — existing usage-section style.
- `notify/version.py` — the one production line this task touches.

---

## Acceptance Criteria

- [ ] Docs state that `template=` accepts a filename **or** Jinja2 source, and list the exact detection rules (`{{`, `{%`, `{#`, line break)
- [ ] Docs document `template_is_source=` with all three states (`None` / `True` / `False`) and the §7 R1 case it exists for
- [ ] Docs document `TemplateParser.from_string(source, *, cache=True)`, `clear_string_cache()`, and the `string_cache_size` kwarg with its default of 128
- [ ] Docs document the widened `Message.template: Union[Path, str]`
- [ ] **The §7 R10 security note appears adjacent to the inline-source usage example**, with the safe/unsafe contrast
- [ ] The §7 R1 `FileNotFoundError` caveat is documented
- [ ] `README.md` contains all three call shapes from the contract above
- [ ] The string `template_string` appears nowhere in the documentation
- [ ] `{{ content }}` is not documented as generally available
- [ ] `notify/version.py` reads `__version__ = "1.6.0"`
- [ ] `git diff --stat notify/version.py` shows exactly 1 insertion and 1 deletion
- [ ] `git diff --name-only` shows only `docs/`, `README.md` and `notify/version.py`
- [ ] Every code example in the docs runs against the implemented API (execute them)
- [ ] Docs build if the project builds them: `cd docs && make html` (skip and note if Sphinx is not installed)

---

## Test Specification

No automated tests. Verify manually:

```bash
# 1. Version bumped, nothing else touched
git diff --stat notify/version.py          # expect: 1 insertion(+), 1 deletion(-)
.venv/bin/python -c "from notify.version import __version__; print(__version__)"
# expect: 1.6.0

# 2. Forbidden strings absent from docs
! grep -rn "template_string" docs/ README.md
! grep -rn "render_string" docs/ README.md

# 3. Every documented example actually runs
.venv/bin/python - <<'PY'
from notify.templates import TemplateParser, is_template_source
# paste each documented snippet here and confirm it executes
PY

# 4. Scope
git diff --name-only                       # expect: docs/*, README.md, notify/version.py
```

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** at `sdd/specs/jinja-string-notify.spec.md` — §2 (usage), §3 Module 5, §7 R1 and R10.
2. **Check dependencies** — TASK-014, TASK-015 and TASK-016 must be in
   `sdd/tasks/completed/`. You are documenting what was actually built, so read
   the implemented code before writing, not just the spec. If TASK-016 was
   dropped, omit the `Message.template` documentation and note it.
3. **Verify the Codebase Contract**:
   - `ls docs/` and read a neighbouring `.rst` before writing any.
   - Confirm the implemented signatures match what you are about to document.
   - **NEVER** document an import, attribute, or method you have not verified.
4. **Update status** in `sdd/tasks/index/jinja-string-notify.json` → `"in-progress"`.
5. **Implement** — docs plus the one-line version bump.
6. **Verify** every acceptance criterion, including running the examples.
7. **Move this file** to `sdd/tasks/completed/TASK-018-docs-and-version-bump.md`.
8. **Update index** → `"done"`.
9. **Fill in the Completion Note** below.

---

## Completion Note

**Completed by**: sdd-worker (Claude)
**Date**: 2026-08-06
**Notes**: Verified doc file split first (`ls docs/`): `api.rst`,
`architecture.rst`, `authors.rst`, `examples.rst`, `index.rst`,
`models.rst`, `providers.rst`, `server.rst`, plus Sphinx machinery — no
`docs/templates.rst`, matching the contract's "Does NOT Exist" list.
Added a new `` `templates` `` subsection to `docs/api.rst` (previously
just stub headers with no content) documenting `is_template_source()`,
`TemplateParser.from_string(source, *, cache=True)`,
`clear_string_cache()`, and the `string_cache_size` kwarg with its default
of 128. Added a new "Template Support" section to `docs/providers.rst`
(placed right after "Common Features", which already lists "Template
support" as a shared capability) documenting the overloaded `template=`,
the exact detection rules, all three `template_is_source=` states, the §7
R1 `FileNotFoundError` caveat, the three canonical usage examples from
spec §2 (used verbatim), the §7 R10 security note placed immediately
adjacent to the inline-source example with the SAFE/UNSAFE contrast, and
a note that OneSignal has no template support (never calls `_prepare_`).
Added a "### Templates ###" section to `README.md` with the same three
call shapes and a condensed security note. Bumped `notify/version.py`
`__version__` from `"1.5.7"` to `"1.6.0"` — the only line changed
(`git diff --stat` confirms 1 insertion / 1 deletion).

Verified acceptance criteria: `grep -rn "template_string" docs/ README.md`
and `grep -rn "render_string"` both empty; `{{ content }}` is not
documented as generally available anywhere; `git diff --name-only` shows
exactly `README.md`, `docs/api.rst`, `docs/providers.rst`,
`notify/version.py`. Executed the `docs/api.rst` code example directly
(`TemplateParser(directory=TEMPLATE_DIR, string_cache_size=256)`,
`is_template_source()` on both a filename and source string,
`from_string()` + `render_async()`) — all assertions passed. The
`docs/providers.rst` / `README.md` usage examples use `Notify("smtp")` /
`Notify("telegram")` illustratively (matching the pre-existing convention
of every other example in `providers.rst`, e.g. `aws`, `slack`, `teams` —
none of those are literally runnable without real credentials/network
either); the underlying three-way dispatch and security-relevant
behaviour those examples describe were already executed and verified
end-to-end by TASK-015's manual checks and TASK-017's full offline test
suite (45 tests, `tests/test_jinja_string_templates.py`). Full suite
`pytest tests/ -v`: 102 passed, 2 xfailed, 2 failed, 3 errors — identical
pre-existing baseline failures (confirmed against `dev`), zero new
failures.

**Deviations from spec**: `cd docs && make html` was not run as literally
specified; instead ran `python -m sphinx -b html . /tmp/notify_docs_build`
directly (Sphinx *is* installed, contrary to the task's "skip and note if
Sphinx is not installed" fallback condition). The build fails with
`ExtensionError: No puede importar la extensión myst_parser (exception:
No module named 'myst_parser')`. Verified this is pre-existing and
unrelated to this task: `docs/conf.py` requires `myst_parser` in its
`extensions` list on baseline `dev` as well (`git show
dev:docs/conf.py | grep myst_parser`), and `myst_parser` is not listed in
`pyproject.toml` at all — a pre-existing docs-tooling gap, not something
this one-line-version-bump-plus-docs task should fix by adding a new
dependency. Flagging for the spec owner / a follow-up: either add
`myst_parser` to `pyproject.toml`'s doc extras, or drop it from
`docs/conf.py`'s `extensions` if it is unused.

**Post-review addendum (2026-08-06)**: the mandatory adversarial
code-review agent correctly flagged that the initial pass documented
everything *except* the widened `notify.models.Message.template` field
(acceptance criterion explicitly requires docs to cover it) — a silently
missed criterion rather than a disclosed trade-off. Fixed in a follow-up
commit by adding a `` `notify.models.Message.template` `` entry to
`docs/api.rst`'s `` `templates` `` section (the file was already in this
task's scope, so no new file was touched), stating the `Union[Path, str]`
widening, that `Message` has no consumers inside `notify/`, and the known
`python-datamodel` coercion caveat (a `str` is currently coerced to
`PosixPath`, matching TASK-016/017's documented finding) so the docs don't
overclaim what the field does today.
