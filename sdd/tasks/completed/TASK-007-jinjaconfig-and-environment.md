# TASK-007: JinjaConfig dataclass + environment construction

**Feature**: FEAT-002 — TemplateParser refactor (homologation with ai-parrot TemplateEngine)
**Spec**: `sdd/specs/templateparser-refactor.spec.md`
**Status**: pending
**Priority**: high
**Estimated effort**: L (4-8h)
**Depends-on**: none
**Assigned-to**: unassigned

---

## Context

Implements **Module 1** of the spec (§3). This is the foundation task: it
replaces the module-level mutable `jinja_config` dict with a `JinjaConfig`
dataclass, builds the layered `ChoiceLoader(DictLoader + FileSystemLoader)`,
makes the template directory optional, and removes the unconditional
`compile_templates()` call from `__init__`.

Every other task in FEAT-002 builds on the constructor and environment this
task produces. Nothing here changes rendered output for a default-constructed
parser — that invariant is the whole point (spec §1 G10, §5).

---

## Scope

- Add `JinjaConfig` dataclass to `notify/templates.py` exactly as specified in
  spec §2 "Data Models", including `optional_extensions`.
- Rewrite `TemplateParser.__init__` to the signature in spec §2 "New Public
  Interfaces", preserving every backward-compatibility rule listed there.
- Build the loader chain `ChoiceLoader([DictLoader({}), FileSystemLoader(dirs)])`;
  fall back to the `DictLoader` alone when there are no directories.
- Support multiple directories via `template_dirs=`, keeping `directory=` as
  the first positional parameter.
- Accept `str` as well as `Path` for every path-like parameter.
- Load `optional_extensions` tolerantly: import each in its own `try/except`,
  log a warning on failure, and continue. Never let a missing third-party
  extension break construction.
- Wire an optional `FileSystemBytecodeCache` when `bytecode_cache_dir=` is given
  (create the directory if absent).
- **Remove** the `env.compile_templates(...)` call from `__init__`.
- Degrade a missing template directory to a `logger.warning` + memory-only mode.
  Restore the old `RuntimeError` only when `strict_directory=True`.
- Expose `autoescape=` and `strict_undefined=` as constructor overrides.
- Deep-copy mutable fields of a caller-supplied `JinjaConfig` so the caller's
  object is never mutated.
- Add a module logger (`navconfig.logging`); the module has none today.
- Keep `jinja_config` exported as a deprecated dict alias derived from
  `JinjaConfig()`.

**NOT in scope**: the new public methods `add_templates` / `add_template_dir` /
`render_string` / `add_filters` / `add_globals` / `compile_directory`
(TASK-008); the `add_filter` and `"NAV: "` defects (TASK-009); the lazy
`TemplateEnv` singleton (TASK-010); the pyproject extra and version bump
(TASK-011); all tests (TASK-012, TASK-013).

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `notify/templates.py` | MODIFY | Add `JinjaConfig`; rewrite `__init__`, loader chain, extension loading, bytecode cache |

---

## Codebase Contract (Anti-Hallucination)

> **CRITICAL**: verified against `dev` on 2026-08-06. Confirm each reference
> with `read`/`grep` before writing code.

### Verified Imports

```python
# Already in notify/templates.py:1-5
from pathlib import Path
from typing import Optional
from collections.abc import Callable
from navconfig import config
from jinja2 import Environment, FileSystemLoader, TemplateError, TemplateNotFound

# New — all ship in jinja2 3.1 (pyproject.toml:41 pins "jinja2>=3.1.4")
from jinja2 import (
    BaseLoader, ChoiceLoader, DictLoader, FileSystemBytecodeCache,
    StrictUndefined, Undefined, select_autoescape,
)
from dataclasses import dataclass, field
from navconfig.logging import logging   # repo-wide logging pattern
```

### Existing Signatures to Use

```python
# notify/templates.py — current state, 130 lines
jinja_config = {                                     # line 7  ← replaced by JinjaConfig
    "enable_async": True,
    "extensions": ["jinja2.ext.i18n", "jinja2.ext.loopcontrols"],
}

class TemplateParser:                                # line 13
    def __init__(self, directory: Path, filters: Optional[list] = None, **kwargs):  # line 20
        self.template = None                         # line 26  ← keep this attribute
        self.path = directory.resolve()              # line 27  ← Path-only today
        self.filters = filters                       # line 28  ← keep this attribute
        # lines 29-32: RuntimeError when directory missing
        # lines 33-36: kwargs["config"] shallow-merged over jinja_config
        # lines 37-41: config.getboolean("TEMPLATE_DEBUG", fallback=False)
        #              → self.config["extensions"].append("jinja2.ext.debug")
        #              ← THIS MUTATES THE SHARED MODULE-LEVEL LIST (the leak to fix)
        # lines 43-45: FileSystemLoader(searchpath=[str(self.path)])
        # lines 49-51: Environment(loader=templateLoader, **self.config)
        # lines 53-58: env.compile_templates(target=<path>/".compiled", zip="deflated")
        #              ← REMOVE from __init__
        # lines 64-65: self.env.filters.update(self.filters) when filters is not None
```

```python
# notify/conf.py:7-10 — the default directory this parser receives
if not (template_dir := config.get('TEMPLATE_DIR')):
    TEMPLATE_DIR = BASE_DIR.joinpath("templates")
else:
    TEMPLATE_DIR = Path(template_dir).resolve()
```

```python
# notify/notify.py:85-87 — the sole production construction site (unchanged by THIS task)
TemplateEnv = TemplateParser(directory=TEMPLATE_DIR)
```

### Does NOT Exist

- ~~`notify.templates.JinjaConfig`~~ — you are creating it.
- ~~`notify.templates.TemplateEngine`~~ — lives ONLY in ai-parrot at
  `packages/ai-parrot/src/parrot/template/engine.py:47`. Do not import, vendor,
  or rename `TemplateParser` to it.
- ~~`self.logger` on `TemplateParser`~~ — the module has no logger today; add one.
- ~~`notify.conf.TEMPLATE_DEBUG`~~ — not defined in `conf.py`. `TEMPLATE_DEBUG`
  is read ad hoc via `config.getboolean` at `templates.py:37-39`.
- ~~`jinja2.ext.debug` as a default extension~~ — it is conditional on
  `TEMPLATE_DEBUG` only.
- ~~`jinja2_time` / `jinja2_iso8601` / `jinja2_humanize_extension` as installed
  packages~~ — none are present in this environment. They MUST be optional.

---

## Implementation Notes

### Pattern to Follow

```python
# Per-instance mutable defaults — never a shared module-level list.
@dataclass
class JinjaConfig:
    template_dirs: list[Path] = field(default_factory=list)
    extensions: list[str] = field(default_factory=lambda: [
        "jinja2.ext.i18n", "jinja2.ext.loopcontrols", "jinja2.ext.do",
    ])
    ...

# Tolerant optional-extension loading — one try/except per extension.
for dotted in cfg.optional_extensions:
    module_name = dotted.rsplit(".", 1)[0]
    try:
        importlib.import_module(module_name)
    except ImportError:
        self.logger.warning(
            "Notify: optional Jinja2 extension %s unavailable; skipping. "
            "Install the 'templates' extra to enable it.", dotted
        )
        continue
    extensions.append(dotted)
```

### Key Constraints

- **Defaults must reproduce 1.5.7 behaviour byte-for-byte.** `autoescape=False`,
  `undefined=jinja2.Undefined`, and `trim_blocks` / `lstrip_blocks` /
  `keep_trailing_newline` all `False`. ai-parrot sets the three whitespace flags
  to `True` (`engine.py:42-44`) — **do NOT copy those values** (spec §7 R1).
- **Never mutate a caller-supplied `JinjaConfig`.** ai-parrot's
  `TemplateEngine.__init__` appends to `cfg.template_dirs` (`engine.py:67-75`),
  so reusing one config across two engines accumulates directories. Copy first
  (spec §7 R7).
- `enable_async=True` stays the default — providers call `render_async()`.
- Google-style docstrings + strict type hints on everything (CLAUDE.md).
- `self.logger`, never `print`.
- Keep `self.template`, `self.path`, `self.filters` and `self.env` as public
  attributes; `self.path` should now point at the FIRST directory (or `None` in
  memory-only mode) so existing attribute reads do not explode.

### References in Codebase

- `notify/templates.py` — the module being refactored.
- `packages/ai-parrot/src/parrot/template/engine.py:56-137` (in the sibling repo
  `../ai-parrot`) — reference implementation of the loader chain and bytecode
  cache. Read it for structure; **do not copy its defaults or its `render()`
  signature**.

---

## Acceptance Criteria

- [ ] `JinjaConfig` exists with the fields and defaults from spec §2
- [ ] `TemplateParser(directory=Path(...))` and `TemplateParser(directory="...")` both construct
- [ ] `TemplateParser()` with no directory constructs in memory-only mode
- [ ] A missing directory logs a warning; `strict_directory=True` raises `RuntimeError`
- [ ] Construction writes NOTHING into the template directory (no `.compiled`)
- [ ] `config={"enable_async": False}` still shallow-merges (legacy dict path)
- [ ] The same `JinjaConfig` passed to two parsers is not mutated
- [ ] `TEMPLATE_DEBUG=True` does not leak `jinja2.ext.debug` into later instances
- [ ] A missing optional extension logs a warning and does not break construction
- [ ] `bytecode_cache_dir=` creates the directory and wires `FileSystemBytecodeCache`
- [ ] `autoescape` is `False` and `undefined` is `Undefined` on a default parser
- [ ] `trim_blocks`, `lstrip_blocks`, `keep_trailing_newline` are all `False` on a default parser
- [ ] `jinja_config` remains importable from `notify.templates`
- [ ] `get_template`, `environment`, `render`, `render_async`, `add_filter` still work unchanged
- [ ] `ruff check notify/templates.py` clean
- [ ] `from notify.templates import TemplateParser, JinjaConfig` works

---

## Test Specification

Tests are written in TASK-012. Verify manually during this task:

```python
from pathlib import Path
from notify.templates import TemplateParser, JinjaConfig

d = Path("/tmp/tpl"); d.mkdir(exist_ok=True)
(d / "hello.html").write_text("Hello {{ name }}!", encoding="utf-8")

p = TemplateParser(directory=d)
assert p.render("hello.html", {"name": "Pilar"}) == "Hello Pilar!"
assert not (d / ".compiled").exists()          # no side-effect artifact
assert p.environment.autoescape is False       # default preserved

cfg = JinjaConfig()
TemplateParser(directory=d, config=cfg)
TemplateParser(directory=d, config=cfg)
assert len(cfg.template_dirs) == 0              # caller config untouched
```

---

## Agent Instructions

1. **Read the spec** — `sdd/specs/templateparser-refactor.spec.md`, especially
   §2 (Data Models, New Public Interfaces), §6 (Codebase Contract) and §7 (Risks).
2. **Check dependencies** — none.
3. **Verify the Codebase Contract** — re-read `notify/templates.py` and confirm
   the line numbers above before editing.
4. **Update status** in `sdd/tasks/index/templateparser-refactor.json` → `in-progress`.
5. **Implement** the scope. Nothing beyond it.
6. **Verify** every acceptance criterion.
7. **Move this file** to `sdd/tasks/completed/TASK-007-jinjaconfig-and-environment.md`.
8. **Update index** → `done`.
9. **Fill in the Completion Note** below.

Use `.venv/bin/python` directly — `.venv/bin/activate` carries a stale
`VIRTUAL_ENV` path (see spec §6 "Does NOT Exist").

---

## Completion Note

**Completed by**: sdd-worker (Claude)
**Date**: 2026-08-06
**Notes**: Implemented `JinjaConfig` dataclass, rewrote `TemplateParser.__init__`
per spec §2, layered `ChoiceLoader(DictLoader + FileSystemLoader)`, tolerant
optional-extension loading, opt-in `FileSystemBytecodeCache`, removed the
unconditional `compile_templates()` call, degraded missing directories to a
warning (with `strict_directory=True` opt-out), and kept `jinja_config` as a
deprecated dict alias. Verified manually: memory-only mode, missing-dir
warning/strict paths, legacy dict `config=` merge, `JinjaConfig` instance not
mutated across two parsers, `TEMPLATE_DEBUG` extension not leaking across
instances, whitespace/autoescape defaults unchanged, no `.compiled` artifact
written. `ruff check notify/templates.py` is clean. Full `pytest tests/ -v`
run: 59 passed, 2 failed + 3 errors — all pre-existing on `dev` baseline
(AWS SES mock region format, Outlook event-loop fixture issue), unrelated to
this change and reproduced identically before this task's edits.

**Deviations from spec**: none
