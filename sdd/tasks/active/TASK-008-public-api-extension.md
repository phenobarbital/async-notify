# TASK-008: Public API extension — in-memory templates, render_string, globals

**Feature**: FEAT-002 — TemplateParser refactor (homologation with ai-parrot TemplateEngine)
**Spec**: `sdd/specs/templateparser-refactor.spec.md`
**Status**: pending
**Priority**: high
**Estimated effort**: M (2-4h)
**Depends-on**: TASK-007
**Assigned-to**: unassigned

---

## Context

Implements **Module 2** of the spec (§3). TASK-007 built the `JinjaConfig`
dataclass and the layered loader; this task exposes the capabilities that
layering makes possible — the seven new public methods that close the gap with
ai-parrot's `TemplateEngine` (spec §1 G1, G2, G3, G4, G7).

---

## Scope

Add to `TemplateParser`:

- `add_template_dir(path)` — append a filesystem directory at runtime and
  rebuild the `ChoiceLoader`.
- `add_templates(templates)` — register/override in-memory templates.
- `add_filters(filters)` — bulk filter registration from a mapping.
- `add_globals(globals_)` — register template globals.
- `render_string(source, params)` — **synchronous** ad-hoc render.
- `render_string_async(source, params)` — coroutine variant.
- `compile_directory(target, *, zip="deflated")` — explicit replacement for the
  `compile_templates()` call removed from `__init__` in TASK-007. No-op when
  there are no filesystem directories.

**NOT in scope**: `JinjaConfig` or constructor changes (TASK-007); the
`add_filter` defect and `"NAV: "` prefix (TASK-009); `notify/notify.py`
(TASK-010); packaging (TASK-011); tests (TASK-012, TASK-013).

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `notify/templates.py` | MODIFY | Add the seven public methods |

---

## Codebase Contract (Anti-Hallucination)

### Verified Imports

```python
# Available after TASK-007
from jinja2 import ChoiceLoader, DictLoader, FileSystemLoader, TemplateError
from typing import Any, Optional, Mapping, Union
from pathlib import Path
```

### Existing Signatures to Use

```python
# notify/templates.py — post-TASK-007 state
class TemplateParser:
    env: Environment                  # the live jinja2 Environment
    path: Optional[Path]              # first template directory, or None
    template: Optional[Template]      # last template fetched (line 26 today)

    def get_template(self, filename: str): ...   # line 67 today
        # raises FileNotFoundError on TemplateNotFound, RuntimeError otherwise

    @property
    def environment(self): ...                   # lines 83-85 today

    def render(self, filename, params=None) -> str: ...        # line 99 today — SYNC
    async def render_async(self, filename, params=None) -> str: ...  # line 112 today
```

```python
# Error-handling shape to mirror in the new methods — notify/templates.py:123-130
except TemplateError as ex:
    raise ValueError(f"Template parsing error, template: {filename}: {ex}") from ex
except Exception as err:
    raise RuntimeError(f"Notify: Error rendering: {filename}, error: {err}") from err
```

### Does NOT Exist

- ~~`TemplateParser.render_string()` / `render_string_async()` / `add_templates()` /
  `add_template_dir()` / `add_filters()` / `add_globals()` / `compile_directory()`~~
  — you are creating all seven.
- ~~`TemplateEngine.render_string()` as a sync method~~ — ai-parrot's version
  (`engine.py:196`) is async-only. async-notify needs BOTH variants.
- ~~`ChoiceLoader.loaders.append(...)` as a supported mutation~~ — rebuild the
  `ChoiceLoader` instead; ai-parrot does exactly this at `engine.py:158-162`.
- ~~`self._dict_loader` before TASK-007~~ — it is introduced by TASK-007.

---

## Implementation Notes

### Pattern to Follow

```python
def add_template_dir(self, path: PathLike) -> None:
    """Add a filesystem directory to the search path at runtime."""
    p = Path(path).resolve()
    if not p.exists() or not p.is_dir():
        raise ValueError(f"Notify: template directory invalid: {p}")
    self._fs_dirs.append(p)
    # Rebuild the chain — carry the EXISTING in-memory mapping across.
    mapping = self._dict_loader.mapping          # <-- must not be dropped
    self._dict_loader = DictLoader(mapping)
    self.env.loader = ChoiceLoader([
        self._dict_loader,
        FileSystemLoader([str(d) for d in self._fs_dirs]),
    ])
```

### Key Constraints

- **`render_string()` must be synchronous** and `render_string_async()` a
  coroutine, mirroring the existing `render()` / `render_async()` split. Do NOT
  follow ai-parrot, where `render()` and `render_string()` are both async
  (spec §1 Non-Goals).
- **Rebuilding the loader must preserve in-memory templates** — dropping
  `self._dict_loader.mapping` silently loses everything registered by
  `add_templates()` (spec §7 R6).
- In-memory templates **shadow** filesystem ones: `DictLoader` comes first in
  the `ChoiceLoader`.
- `compile_directory()` returns silently when `self._fs_dirs` is empty.
- `add_filters` / `add_globals` write into `self.env.filters` / `self.env.globals`.
- Google-style docstrings + type hints; `self.logger` for warnings.

### References in Codebase

- `packages/ai-parrot/src/parrot/template/engine.py:151-242` (sibling repo
  `../ai-parrot`) — reference for `add_template_dir`, `add_templates`,
  `render_string`, `add_filters`, `add_globals`, `compile_directory`. Mirror the
  structure; **change `render_string` to provide a sync variant**.

---

## Acceptance Criteria

- [ ] All seven methods exist with the signatures in spec §2 "New Public Interfaces"
- [ ] `add_templates({"inline.html": "Hi {{ who }}"})` then `render("inline.html", {"who": "x"})` works
- [ ] An in-memory template shadows a filesystem template of the same name
- [ ] `add_template_dir()` resolves templates from the new directory
- [ ] `add_template_dir()` does NOT drop templates previously added via `add_templates()`
- [ ] With two directories holding the same filename, the first registered wins
- [ ] `render_string("Hi {{ who }}", {"who": "there"})` returns `"Hi there"` synchronously
- [ ] `await render_string_async(...)` returns the same value
- [ ] `add_globals({"app": "notify"})` makes `{{ app }}` resolve
- [ ] `add_filters({"upper2": str.upper})` registers the filter
- [ ] `compile_directory(tmp)` produces the artifact; no-ops with no directories
- [ ] `ruff check notify/templates.py` clean

---

## Test Specification

Tests are written in TASK-012. Verify manually:

```python
p = TemplateParser(directory=d)
p.add_templates({"inline.html": "Hi {{ who }}"})
assert p.render("inline.html", {"who": "there"}) == "Hi there"
assert p.render_string("A {{ b }}", {"b": "c"}) == "A c"

p.add_template_dir(other_dir)
assert p.render("inline.html", {"who": "still"}) == "Hi still"   # memory survived
```

---

## Agent Instructions

1. **Read the spec** — §2 "New Public Interfaces", §7 R6.
2. **Check dependencies** — TASK-007 must be in `sdd/tasks/completed/`.
3. **Verify the Codebase Contract** — re-read `notify/templates.py` post-TASK-007.
4. **Update status** in `sdd/tasks/index/templateparser-refactor.json` → `in-progress`.
5. **Implement** the scope. Nothing beyond it.
6. **Verify** every acceptance criterion.
7. **Move this file** to `sdd/tasks/completed/TASK-008-public-api-extension.md`.
8. **Update index** → `done`.
9. **Fill in the Completion Note**.

Use `.venv/bin/python` directly — `.venv/bin/activate` is stale.

---

## Completion Note

*(Agent fills this in when done)*

**Completed by**: <session or agent ID>
**Date**: YYYY-MM-DD
**Notes**:

**Deviations from spec**: none | describe if any
