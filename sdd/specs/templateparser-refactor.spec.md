---
# FEAT-145 flow-type fields.
# Feature work bases on dev — no production hotfix involved.
type: feature
base_branch: dev
---

# Feature Specification: TemplateParser refactor — homologation with ai-parrot TemplateEngine

**Feature ID**: FEAT-002
**Date**: 2026-08-06
**Author**: Jesus Lara
**Status**: draft
**Target version**: 1.6.0

---

## 1. Motivation & Business Requirements

### Problem Statement

`notify/templates.py` defines `TemplateParser`, the single Jinja2 entry point
for every template-rendering provider in async-notify. It is the older and
battle-tested of the two Jinja2 wrappers in the ecosystem, but it has stood
still while the sibling implementation in ai-parrot
(`packages/ai-parrot/src/parrot/template/engine.py`, class `TemplateEngine`)
accumulated capabilities and hardening. A comparative audit of both modules
surfaced the following gaps in `TemplateParser`:

1. **Single template directory.** `FileSystemLoader` is built from exactly one
   path (`notify/templates.py:43-45`). There is no way to layer a project's
   templates over a set of library defaults, and no way to register a directory
   after construction.
2. **No in-memory templates.** Every template must exist on disk. Callers that
   hold template source as a string (DB-backed templates, per-tenant overrides,
   test fixtures) have no supported path.
3. **Unconditional compilation with a filesystem side effect.**
   `__init__` always calls
   `env.compile_templates(target=<template_dir>/".compiled", zip="deflated")`
   (`notify/templates.py:53-58`). Constructing a parser writes a zip archive
   *into the template directory itself* — surprising, slow on cold start, and
   hostile to read-only mounts and container images.
4. **No `render_string`.** Ad-hoc or injected template source cannot be
   rendered at all.
5. **Global mutable configuration.** `jinja_config` is a module-level dict
   (`notify/templates.py:7-10`) mutated in place — `self.config["extensions"].append(...)`
   at line 41 appends to the shared list, so enabling `TEMPLATE_DEBUG` leaks
   `jinja2.ext.debug` into every subsequently constructed parser in the process.
6. **No environment tuning surface.** `autoescape`, `undefined`, `trim_blocks`,
   `lstrip_blocks` and `keep_trailing_newline` are never configured, so they sit
   at Jinja2 defaults with no supported way to change them. In particular
   `autoescape` is `False` while providers render **HTML email bodies**
   (`notify/providers/mail.py:152`, `notify/providers/smtp/smtp.py:189`).
7. **No globals, no bulk filter registration.** Only `add_filter()` exists, and
   it is broken (see below). There is no `add_globals()`.
8. **Import-time fragility.** `notify/notify.py:83-87` constructs the
   `TemplateEnv` singleton at module import, and `TemplateParser.__init__`
   raises `RuntimeError` when the directory is absent
   (`notify/templates.py:29-32`). Importing `notify` in an environment without
   a `templates/` directory therefore fails outright.

Two defects were found in the same module during the audit:

- **`add_filter()` is unconditionally broken when `name` is omitted.**
  `notify/templates.py:94` reads `filter_name = name.__name__` inside the
  `elif callable(func):` branch, where `name` is provably `None`. Any call
  to `add_filter(func)` raises `AttributeError: 'NoneType' object has no
  attribute '__name__'`. It should read `func.__name__`. The method currently
  has no callers in the repository, so the bug is latent rather than active.
- **Inconsistent error prefix.** `notify/templates.py:129` raises with a
  `"NAV: "` prefix while every other error in the module uses `"Notify: "`.

### Goals

- **G1** — Multiple template directories, plus `add_template_dir()` at runtime.
- **G2** — In-memory templates via a `DictLoader` layered ahead of the
  filesystem loader, exposed as `add_templates(mapping)`.
- **G3** — `render_string()` / `render_string_async()` for ad-hoc source.
- **G4** — Replace the forced `compile_templates()` in `__init__` with an
  opt-in `FileSystemBytecodeCache` plus an explicit `compile_directory()`.
- **G5** — Replace the module-level `jinja_config` dict with a `JinjaConfig`
  dataclass that cannot leak state between instances.
- **G6** — Expose `autoescape`, `undefined`, `trim_blocks`, `lstrip_blocks`
  and `keep_trailing_newline` as configuration, **defaulting to today's
  effective behaviour**.
- **G7** — Add `add_filters(mapping)` and `add_globals(mapping)`; fix
  `add_filter()`.
- **G8** — Make `TemplateEnv` lazily initialised and tolerate an absent
  template directory (warning + memory-only mode instead of `RuntimeError`).
- **G9** — Optional third-party extensions (`jinja2_time`, `jinja2_iso8601`,
  `jinja2_humanize_extension`) declared as a pyproject extra and loaded
  tolerantly, never as a hard import.
- **G10** — Preserve the existing public API surface with byte-identical
  rendering behaviour under default configuration.

### Non-Goals (explicitly out of scope)

- **Adopting ai-parrot's async-only `render()` signature.** In `TemplateEngine`
  `render()` is a coroutine; in `TemplateParser` it is synchronous. The
  async-notify meaning is authoritative here and does not change.
- **Turning `autoescape` or `StrictUndefined` on by default.** Both would alter
  the rendered output of existing production email templates. They ship as
  opt-in only; flipping the defaults is a 2.0.0 conversation.
- **Changing `trim_blocks` / `lstrip_blocks` / `keep_trailing_newline`
  defaults.** ai-parrot sets all three to `True`; Jinja2's defaults are
  `False`. Adopting ai-parrot's values would silently change whitespace in
  every rendered email. They become configurable, not re-defaulted.
- **Extracting a shared template package used by both repositories.** Worth
  doing eventually, but this spec homologates behaviour inside async-notify only.
- **Fixing the sync-render-inside-a-running-loop hazard.** See §7 Risk R4 —
  pre-existing, documented, not addressed here.
- **Refactoring provider `_render_` methods.** They keep calling
  `Template.render()` / `Template.render_async()` exactly as today.

---

## 2. Architectural Design

### Overview

`notify/templates.py` grows from a 130-line single-class module into a
configuration-driven wrapper, keeping `TemplateParser` as the one public name.
The refactor is additive: every existing attribute, property and method keeps
its name, signature and semantics, and the default-constructed parser produces
output identical to today's.

Three structural changes carry the feature:

1. **`JinjaConfig` dataclass** replaces the mutable module-level `jinja_config`
   dict. Defaults are chosen to reproduce current behaviour exactly — notably
   `autoescape=False`, `undefined=jinja2.Undefined`, and all three whitespace
   flags `False`. `field(default_factory=...)` guarantees per-instance lists,
   which removes the `TEMPLATE_DEBUG` extension-leak described in §1.5. The
   constructor **must not mutate a caller-supplied `JinjaConfig`** — it deep-copies
   the mutable fields first (this is a live bug in ai-parrot's `TemplateEngine`,
   `engine.py:67-75`, and must not be replicated).

2. **Layered loader.** `ChoiceLoader([DictLoader, FileSystemLoader])` — in-memory
   templates shadow filesystem ones, and the filesystem loader spans an ordered
   list of directories. With no directories at all the parser still works in
   memory-only mode.

3. **Opt-in compilation.** `compile_templates()` leaves `__init__` entirely.
   Callers wanting persistent bytecode pass `bytecode_cache_dir=`, which wires a
   `FileSystemBytecodeCache`; callers wanting the old zip artifact call
   `compile_directory(target)` explicitly. This is a deliberate,
   user-approved behavioural change (§8 Q1).

### Component Diagram

```
                    ┌─────────────────┐
                    │   JinjaConfig   │  dataclass, per-instance defaults
                    │  (frozen-ish)   │  autoescape=False, undefined=Undefined
                    └────────┬────────┘
                             │ consumed by
                             ▼
notify/conf.py          ┌─────────────────────────────────┐
  TEMPLATE_DIR ────────▶│        TemplateParser           │
  TEMPLATE_DEBUG        │                                 │
                        │  env: jinja2.Environment        │
                        │   └─ ChoiceLoader               │
                        │       ├─ DictLoader   (memory)  │
                        │       └─ FileSystemLoader(dirs) │
                        │   └─ FileSystemBytecodeCache?   │
                        └────────┬────────────────────────┘
                                 │ exposed via lazy singleton
                                 ▼
                        notify/notify.py
                          __getattr__("TemplateEnv")  ← PEP 562
                                 │
                                 ▼
                        notify/providers/base.py:66
                          self._tpl = TemplateEnv
                          self._tpl.get_template(name)  ← :142
                                 │
                                 ▼
                        jinja2.Template
                          .render()        ← base.py:164, smtp.py:189
                          .render_async()  ← base.py:184, mail.py:152, …
```

### Integration Points

| Existing Component | Integration Type | Notes |
|---|---|---|
| `notify/templates.py::TemplateParser` | **refactors** | Same class name; API extended, not broken. |
| `notify/notify.py::TemplateEnv` | **replaces** | Eager module-level construction (`notify.py:83-87`) becomes PEP 562 lazy `__getattr__`. The `TemplateEnv = None` binding at `notify.py:10` **must be deleted** or `__getattr__` will never fire. |
| `notify/providers/base.py::ProviderBase.__init__` | **unchanged** | `from notify.notify import TemplateEnv` at `base.py:66` keeps working through the module `__getattr__`. |
| `notify/providers/base.py:142` | **unchanged** | `self._tpl.get_template(template)` — the only internal consumer of the parser. |
| `notify/conf.py::TEMPLATE_DIR` | **unchanged** | Still the default directory; now tolerated when missing. |
| `pyproject.toml` | **extends** | New `[project.optional-dependencies] templates` extra. |

### Data Models

```python
# notify/templates.py
PathLike = Union[str, Path]

@dataclass
class JinjaConfig:
    """Configuration for the Jinja2 Environment behind TemplateParser.

    Every default reproduces async-notify's behaviour as of 1.5.7.
    """
    template_dirs: list[Path] = field(default_factory=list)
    extensions: list[str] = field(default_factory=lambda: [
        "jinja2.ext.i18n",
        "jinja2.ext.loopcontrols",
        "jinja2.ext.do",          # native, dependency-free — new in 1.6.0
    ])
    optional_extensions: list[str] = field(default_factory=lambda: [
        "jinja2_time.TimeExtension",
        "jinja2_iso8601.ISO8601Extension",
        "jinja2_humanize_extension.HumanizeExtension",
    ])
    enable_async: bool = True          # unchanged from jinja_config
    autoescape: Any = False            # OPT-IN: matches today's effective value
    undefined: Any = Undefined         # OPT-IN StrictUndefined; permissive today
    trim_blocks: bool = False          # Jinja2 default — NOT ai-parrot's True
    lstrip_blocks: bool = False        # Jinja2 default — NOT ai-parrot's True
    keep_trailing_newline: bool = False # Jinja2 default — NOT ai-parrot's True
    bytecode_cache_dir: Optional[Path] = None
    bytecode_cache_pattern: str = "%s.cache"
```

### New Public Interfaces

```python
class TemplateParser:
    def __init__(
        self,
        directory: Optional[PathLike] = None,
        filters: Optional[Union[list, Mapping[str, Callable]]] = None,
        *,
        template_dirs: Optional[Sequence[PathLike]] = None,
        globals_: Optional[Mapping[str, Any]] = None,
        config: Optional[Union[JinjaConfig, dict]] = None,
        bytecode_cache_dir: Optional[PathLike] = None,
        autoescape: Optional[Union[bool, Callable]] = None,
        strict_undefined: bool = False,
        strict_directory: bool = False,
        **kwargs,
    ) -> None: ...

    # --- preserved surface (signatures unchanged) ---
    def get_template(self, filename: str): ...
    @property
    def environment(self) -> Environment: ...
    def add_filter(self, func: Callable, name: Optional[str] = None) -> None: ...
    def render(self, filename: str, params: Optional[dict] = None) -> str: ...
    async def render_async(self, filename: str, params: Optional[dict] = None) -> str: ...

    # --- new in 1.6.0 ---
    def add_template_dir(self, path: PathLike) -> None: ...
    def add_templates(self, templates: Mapping[str, str]) -> None: ...
    def add_filters(self, filters: Mapping[str, Callable]) -> None: ...
    def add_globals(self, globals_: Mapping[str, Any]) -> None: ...
    def render_string(self, source: str, params: Optional[dict] = None) -> str: ...
    async def render_string_async(self, source: str, params: Optional[dict] = None) -> str: ...
    def compile_directory(self, target: PathLike, *, zip: Optional[str] = "deflated") -> None: ...
```

**Backward-compatibility contract for `__init__`:**

- `directory` stays the first positional parameter and still accepts a `Path`.
  It additionally accepts `str`, and becomes optional.
- `filters` stays the second positional parameter. Today it is typed `list` but
  is passed straight into `env.filters.update()` (`templates.py:65`), which only
  works for a mapping. Accept both: a mapping updates directly; a list/sequence
  of callables is registered by `func.__name__`.
- `config=` as a **dict** keeps its legacy meaning — shallow-merged over the
  defaults, as `templates.py:33-36` does today. As a `JinjaConfig` it is used
  directly (after copying).
- The module-level `jinja_config` dict remains exported as a deprecated alias
  built from `JinjaConfig()`, so `from notify.templates import jinja_config`
  keeps working.

---

## 3. Module Breakdown

### Module 1: `JinjaConfig` dataclass + environment construction
- **Path**: `notify/templates.py`
- **Responsibility**: Introduce the dataclass, tolerant optional-extension
  loading, the `ChoiceLoader(DictLoader + FileSystemLoader)` chain, optional
  `FileSystemBytecodeCache`, and removal of `compile_templates()` from
  `__init__`. Preserve legacy `directory=` / `filters=` / `config=dict` handling.
- **Depends on**: nothing new inside the repo.

### Module 2: Public API extension
- **Path**: `notify/templates.py`
- **Responsibility**: `add_template_dir`, `add_templates`, `add_filters`,
  `add_globals`, `render_string`, `render_string_async`, `compile_directory`.
- **Depends on**: Module 1.

### Module 3: Defect fixes
- **Path**: `notify/templates.py`
- **Responsibility**: Fix `add_filter` (`:94`, `name.__name__` → `func.__name__`,
  plus raise `TypeError` when `func` is not callable); normalise the `"NAV: "`
  error prefix at `:129` to `"Notify: "`.
- **Depends on**: Module 2 (`add_filter` delegates to `add_filters`).

### Module 4: Lazy `TemplateEnv` singleton
- **Path**: `notify/notify.py`
- **Responsibility**: Delete `TemplateEnv = None` (`:10`) and the
  `if __name__ == "notify.notify":` block (`:83-87`); add a PEP 562 module-level
  `__getattr__` that builds and memoises the parser on first attribute access.
  Absent `TEMPLATE_DIR` logs a warning and yields a memory-only parser.
- **Depends on**: Module 1 (needs the tolerant-directory behaviour).

### Module 5: Packaging extra
- **Path**: `pyproject.toml`
- **Responsibility**: Add `[project.optional-dependencies] templates` listing
  the three third-party Jinja2 extensions. Verify exact distribution names and
  floors on PyPI before pinning (see §6 "Does NOT Exist").
- **Depends on**: Module 1.

### Module 6: Test suite
- **Path**: `tests/test_templates.py`
- **Responsibility**: Offline unit tests covering §4.
- **Depends on**: Modules 1–5.

---

## 4. Test Specification

All tests are offline — no network, no SMTP, no external services. Template
directories are built with `tmp_path`.

### Unit Tests

| Test | Module | Description |
|---|---|---|
| `test_init_legacy_directory_path` | 1 | `TemplateParser(directory=Path(...))` still constructs and finds templates. |
| `test_init_accepts_str_directory` | 1 | `directory=` accepts `str` as well as `Path`. |
| `test_init_missing_dir_warns_not_raises` | 1 | Absent directory logs a warning and yields a memory-only parser; `strict_directory=True` restores the `RuntimeError`. |
| `test_init_does_not_write_compiled_artifact` | 1 | After construction, no `.compiled` entry exists in the template dir. |
| `test_config_dict_legacy_merge` | 1 | `config={"enable_async": False}` shallow-merges over defaults. |
| `test_config_instance_not_mutated` | 1 | The same `JinjaConfig` passed to two parsers does not accumulate `template_dirs`. |
| `test_template_debug_does_not_leak` | 1 | With `TEMPLATE_DEBUG=True`, a second default-constructed parser does not inherit `jinja2.ext.debug`. |
| `test_optional_extension_missing_is_tolerated` | 1 | A missing third-party extension is skipped with a warning; construction succeeds. |
| `test_multiple_template_dirs_precedence` | 1 | With two dirs holding the same filename, the first wins. |
| `test_add_template_dir_runtime` | 2 | A directory added post-construction resolves its templates. |
| `test_add_templates_in_memory` | 2 | An in-memory template renders. |
| `test_in_memory_shadows_filesystem` | 2 | An in-memory template with the same name takes precedence over the on-disk one. |
| `test_render_sync_backward_compat` | 2 | `render(name, params)` returns the same string as 1.5.7 for a fixture template. |
| `test_render_async_backward_compat` | 2 | `await render_async(name, params)` matches `render()` output. |
| `test_render_string_sync_and_async` | 2 | Both variants render `"Hi {{ who }}"`. |
| `test_add_globals` | 2 | A registered global is visible to templates. |
| `test_add_filters_mapping` | 2 | Bulk filter registration works. |
| `test_get_template_missing_raises_filenotfound` | 2 | `get_template("nope.html")` raises `FileNotFoundError` (unchanged). |
| `test_environment_property` | 2 | `environment` returns the live `jinja2.Environment`. |
| `test_compile_directory_explicit` | 2 | `compile_directory(tmp_path)` produces the artifact on demand. |
| `test_bytecode_cache_opt_in` | 2 | `bytecode_cache_dir=` creates the dir and populates it after a render. |
| **`test_add_filter_without_name_uses_func_name`** | 3 | **Regression for the `:94` bug** — `add_filter(my_filter)` registers under `"my_filter"` instead of raising `AttributeError`. |
| `test_add_filter_with_explicit_name` | 3 | Explicit `name=` still wins. |
| `test_add_filter_non_callable_raises_typeerror` | 3 | Non-callable input raises `TypeError`. |
| `test_error_prefix_is_notify` | 3 | A render failure message starts with `"Notify:"`, never `"NAV:"`. |
| `test_autoescape_off_by_default` | 1 | `{{ "<b>x</b>" }}` renders unescaped — proves the production default is untouched. |
| `test_autoescape_opt_in` | 1 | `autoescape=True` escapes the same input. |
| `test_undefined_permissive_by_default` | 1 | A missing variable renders as empty string. |
| `test_strict_undefined_opt_in` | 1 | `strict_undefined=True` raises on a missing variable. |
| `test_whitespace_defaults_unchanged` | 1 | `trim_blocks` / `lstrip_blocks` / `keep_trailing_newline` are all `False` on a default parser. |

### Integration Tests

| Test | Description |
|---|---|
| `test_template_env_lazy_not_built_on_import` | Importing `notify.notify` does not construct a parser (assert via a patched `TemplateParser.__init__` counter). |
| `test_template_env_memoised` | Two `TemplateEnv` accesses return the same object. |
| `test_import_notify_without_templates_dir` | With `TEMPLATE_DIR` pointing at a nonexistent path, `import notify` succeeds. |
| `test_provider_base_get_template_still_works` | A `ProviderBase` subclass resolves a template through `self._tpl.get_template()` exactly as before. |

### Test Data / Fixtures

```python
@pytest.fixture
def template_dir(tmp_path):
    """Minimal on-disk template set."""
    d = tmp_path / "templates"
    d.mkdir()
    (d / "hello.html").write_text("Hello {{ name }}!", encoding="utf-8")
    (d / "raw.html").write_text("{{ value }}", encoding="utf-8")
    return d


@pytest.fixture
def parser(template_dir):
    from notify.templates import TemplateParser
    return TemplateParser(directory=template_dir)
```

---

## 5. Acceptance Criteria

> This feature is complete when ALL of the following are true:

- [ ] All unit tests pass (`.venv/bin/python -m pytest tests/test_templates.py -v`)
- [ ] The pre-existing suite still passes (`.venv/bin/python -m pytest tests/ -v`), with no new failures versus the 1.5.7 baseline
- [ ] `TemplateParser(directory=<Path>)` constructs, and `get_template`, `render`, `render_async`, `environment` and `add_filter` keep their 1.5.7 signatures and semantics
- [ ] `render()` remains **synchronous** and `render_async()` remains a coroutine — ai-parrot's async-only `render()` is NOT adopted
- [ ] Constructing a `TemplateParser` writes nothing into the template directory (no `.compiled` artifact)
- [ ] `compile_directory()` reproduces the old artifact when called explicitly
- [ ] `bytecode_cache_dir=` wires a `FileSystemBytecodeCache` and populates the directory after a render
- [ ] Multiple directories, `add_template_dir()`, `add_templates()`, `render_string()`, `render_string_async()`, `add_filters()` and `add_globals()` all work as specified in §2
- [ ] `autoescape` is `False` and `undefined` is permissive on a default-constructed parser; both are reachable via `autoescape=` / `strict_undefined=`
- [ ] `trim_blocks`, `lstrip_blocks` and `keep_trailing_newline` are all `False` on a default-constructed parser
- [ ] Passing the same `JinjaConfig` to two parsers does not mutate it
- [ ] `TEMPLATE_DEBUG=True` does not leak `jinja2.ext.debug` into later parser instances
- [ ] `add_filter(func)` without an explicit name registers under `func.__name__` (regression test for `templates.py:94`)
- [ ] No error message in `notify/templates.py` uses the `"NAV: "` prefix
- [ ] Importing `notify` succeeds when `TEMPLATE_DIR` does not exist, emitting a warning
- [ ] `from notify.notify import TemplateEnv` still works and the parser is built lazily on first access, then memoised
- [ ] The three third-party extensions are declared under a `templates` extra in `pyproject.toml` and their absence never breaks construction
- [ ] `notify/version.py` is bumped to `1.6.0`
- [ ] No breaking changes to the existing public API
- [ ] Docstrings are Google-style with type hints on every new/changed method

---

## 6. Codebase Contract

> **CRITICAL — Anti-Hallucination Anchor**
> This section is the single source of truth for what exists in the codebase.
> Implementation agents MUST NOT reference imports, attributes, or methods
> not listed here without first verifying they exist via `grep` or `read`.

### Verified Imports

```python
# All verified 2026-08-06 against the working tree at dev@ba105a6
from notify.templates import TemplateParser, jinja_config  # notify/templates.py:13, :7
from notify.conf import TEMPLATE_DIR                       # notify/conf.py:7-10
from notify.notify import Notify, TemplateEnv, LoadProvider # notify/notify.py:12, :10, :64
from notify.providers.base import ProviderBase             # notify/providers/base.py

# Third-party, already hard dependencies (pyproject.toml:41 → "jinja2>=3.1.4")
from jinja2 import (
    Environment, FileSystemLoader, TemplateError, TemplateNotFound,  # used today, templates.py:5
    BaseLoader, ChoiceLoader, DictLoader, FileSystemBytecodeCache,   # new usage, all in jinja2 3.1
    StrictUndefined, Undefined, select_autoescape,
)
from navconfig import config          # notify/templates.py:4
from navconfig.logging import logging # pattern used across the repo
```

### Existing Class Signatures

```python
# notify/templates.py  (130 lines total)
jinja_config = {                                            # line 7
    "enable_async": True,
    "extensions": ["jinja2.ext.i18n", "jinja2.ext.loopcontrols"],
}

class TemplateParser:                                       # line 13
    def __init__(self, directory: Path, filters: Optional[list] = None, **kwargs):  # line 20
        self.template = None                                # line 26
        self.path = directory.resolve()                     # line 27  ← Path-only today
        self.filters = filters                              # line 28
        # RuntimeError when the directory is absent          # lines 29-32
        # "config" kwarg shallow-merged over jinja_config    # lines 33-36
        # navconfig TEMPLATE_DEBUG appends jinja2.ext.debug  # lines 37-41 (mutates shared list)
        # FileSystemLoader(searchpath=[str(self.path)])      # lines 43-45
        self.env: Optional[Environment] = Environment(...)  # lines 49-51
        # env.compile_templates(target=<path>/".compiled", zip="deflated")  # lines 53-58
        # env.filters.update(self.filters) when filters is not None         # lines 64-65

    def get_template(self, filename: str): ...              # line 67  → FileNotFoundError / RuntimeError
    @property
    def environment(self): ...                              # line 83-85
    def add_filter(self, func: Callable, name: Optional[str] = None) -> None: ...  # line 87
                                                            # line 94 ← DEFECT: name.__name__
    def render(self, filename: str, params: Optional[dict] = None) -> str: ...        # line 99  (SYNC)
    async def render_async(self, filename: str, params: Optional[dict] = None) -> str: ...  # line 112
                                                            # line 129 ← DEFECT: "NAV: " prefix
```

```python
# notify/notify.py
PROVIDERS = {}                                              # line 9
TemplateEnv = None                                          # line 10  ← must be DELETED for PEP 562
class Notify: ...                                           # line 12
def LoadProvider(provider: str): ...                        # line 64
if __name__ == "notify.notify":                             # line 83  ← eager init block
    TemplateEnv = TemplateParser(directory=TEMPLATE_DIR)    # lines 85-87
```

```python
# notify/conf.py
if not (template_dir := config.get('TEMPLATE_DIR')):        # line 7
    TEMPLATE_DIR = BASE_DIR.joinpath("templates")           # line 8
else:
    TEMPLATE_DIR = Path(template_dir).resolve()             # line 10
```

```python
# notify/providers/base.py
from notify.notify import TemplateEnv   # line 66, inside ProviderBase.__init__ try-block
self._tpl = TemplateEnv                 # line 67
self._template = None                   # line 68
# RuntimeError("Notify: Can't load the Jinja2 Template Parser: ...")  # lines 69-72

async def _prepare_(self, recipient=None, message=None, template: str = None, **kwargs):  # line 116
    self._template = self._tpl.get_template(template)   # line 142  ← ONLY internal parser call

def _render_sync_(self, to=None, message=None, subject=None, **kwargs):  # line 147 — no callers
    msg = self._template.render(**self._templateargs)   # line 164  ← jinja2.Template.render

async def _render_(self, to=None, message=None, subject=None, **kwargs):  # line 167
    msg = await self._template.render_async(**self._templateargs)  # line 184
```

### Integration Points

| New Component | Connects To | Via | Verified At |
|---|---|---|---|
| `JinjaConfig` | `TemplateParser.__init__` | dataclass argument | `notify/templates.py:20` |
| `TemplateParser` (memory-only mode) | `notify.notify.__getattr__` | lazy construction | `notify/notify.py:83-87` (block being replaced) |
| `notify.notify.__getattr__` | `ProviderBase.__init__` | `from notify.notify import TemplateEnv` | `notify/providers/base.py:66` |
| `TemplateParser.get_template()` | `ProviderBase._prepare_` | method call | `notify/providers/base.py:142` |
| `templates` extra | `JinjaConfig.optional_extensions` | tolerant import | `pyproject.toml:41` (jinja2 pin) |

### Consumers of the rendering path (all UNCHANGED by this spec)

Verified via `grep -rn 'self\._template\.' notify/`:

| File | Line | Call |
|---|---|---|
| `notify/providers/base.py` | 164 | `self._template.render(...)` — sync |
| `notify/providers/base.py` | 184 | `await self._template.render_async(...)` |
| `notify/providers/smtp/smtp.py` | 189 | `self._template.render(...)` — sync |
| `notify/providers/mail.py` | 152 | `await self._template.render_async(...)` |
| `notify/providers/ses/ses.py` | 104 | `await self._template.render_async(...)` |
| `notify/providers/gmail/gmail.py` | 84 | `await self._template.render_async(...)` |
| `notify/providers/outlook/outlook.py` | 146 | `await self._template.render_async(...)` |
| `notify/providers/office365/office365.py` | 166 | `await self._template.render_async(...)` |

All eight are calls on the **`jinja2.Template` object** returned by
`get_template()`, NOT on `TemplateParser`.

### Does NOT Exist (Anti-Hallucination)

- ~~`TemplateParser.render_string()`~~ — being added by this spec; absent in 1.5.7.
- ~~`TemplateParser.add_templates()` / `add_template_dir()` / `add_filters()` / `add_globals()` / `compile_directory()`~~ — all new here.
- ~~`notify.templates.JinjaConfig`~~ — new; today configuration is the `jinja_config` dict at `templates.py:7`.
- ~~`notify.templates.TemplateEngine`~~ — **does not exist in async-notify.** `TemplateEngine` lives only in ai-parrot at `packages/ai-parrot/src/parrot/template/engine.py:47`. Do not import it, do not vendor it, do not rename `TemplateParser` to it.
- ~~`TemplateParser.render()` as a coroutine~~ — it is and stays synchronous. ai-parrot's `TemplateEngine.render()` IS async (`engine.py:181`); that signature must NOT be copied.
- ~~Any caller of `TemplateParser.render()` or `TemplateParser.render_async()` inside this repo~~ — verified none. Only `get_template()` is consumed internally (`base.py:142`).
- ~~`ProviderBase._render_sync_()` callers~~ — verified none; the method is defined at `base.py:147` and never invoked.
- ~~`notify/conf.py::TEMPLATE_DEBUG`~~ — not defined in `conf.py`. `TEMPLATE_DEBUG` is read ad hoc via `config.getboolean` inside `templates.py:37-39`.
- ~~`tests/test_templates.py`~~ — does not exist yet; current suite is `tests/test_email_utf8.py`, `test_outlook.py`, `test_outlook1.py`, `test_ses.py`, plus `tests/sdd_scripts/`.
- ~~`jinja2-time` / `jinja2-iso8601` / `jinja2-humanize-extension` as installed packages~~ — none present in this environment, and **none declared in any `pyproject.toml` in ai-parrot either** (verified by exhaustive grep). Their exact PyPI distribution names and version floors are **(unverified — check before use)** and must be confirmed against PyPI before being written into the extra.
- ~~`.venv/bin/activate` as a usable activation script~~ — the venv's `activate` carries a stale `VIRTUAL_ENV=/home/jesuslara/proyectos/navigator/notify/.venv`. Use `.venv/bin/python` directly, or recreate the venv with `uv venv`.

---

## 7. Implementation Notes & Constraints

### Patterns to Follow

- Google-style docstrings with strict type hints on every new/changed method
  (CLAUDE.md → Code Standards).
- `self.logger` (`navconfig.logging`) for warnings — never `print`. The current
  module has no logger; add one.
- Dataclasses for structured configuration; `field(default_factory=...)` for
  every mutable default.
- Keep the module import-safe: no filesystem writes and no exceptions at import
  time.
- Package management via `uv`; the venv interpreter is `.venv/bin/python`
  (see §6 — `activate` is stale).

### Known Risks / Gotchas

- **R1 — Silent whitespace regressions.** ai-parrot sets `trim_blocks`,
  `lstrip_blocks` and `keep_trailing_newline` to `True`. Copying those defaults
  would change the rendered bytes of every existing email template without any
  test failing. *Mitigation*: defaults pinned to Jinja2's `False`;
  `test_whitespace_defaults_unchanged` asserts it.
- **R2 — Autoescape is a behavioural switch, not a pure hardening.** Turning it
  on would double-escape templates that already emit pre-escaped HTML.
  *Mitigation*: opt-in only, with `test_autoescape_off_by_default` guarding the
  default.
- **R3 — Removing `compile_templates()` from `__init__` is observable.**
  Deployments relying on the `.compiled` artifact appearing as a side effect
  will no longer get it. *Mitigation*: `compile_directory()` reproduces it on
  demand; call it out in the release notes for 1.6.0.
- **R4 — Pre-existing: sync render inside a running event loop.** With
  `enable_async=True`, `jinja2.Template.render()` runs
  `loop.run_until_complete(...)`, which raises `RuntimeError` if a loop is
  already running. This affects `smtp.py:189` and `base.py:164` today and is
  **out of scope**; do not attempt to fix it here, but do not make it worse.
- **R5 — PEP 562 `__getattr__` only fires for names absent from the module.**
  Leaving `TemplateEnv = None` at `notify/notify.py:10` in place would make the
  lazy singleton dead code that always returns `None`. Deleting that line is
  mandatory, not cosmetic.
- **R6 — `DictLoader` mutation.** `add_templates()` writes into
  `self._dict_loader.mapping`. `add_template_dir()` rebuilds the `ChoiceLoader`
  and must carry the existing mapping across, or in-memory templates registered
  earlier silently disappear (this is how ai-parrot handles it at
  `engine.py:158-162`).
- **R7 — Caller-config mutation.** ai-parrot's `TemplateEngine.__init__` appends
  to `cfg.template_dirs` on a caller-supplied `JinjaConfig`
  (`engine.py:67-75`), so reusing one config across two engines accumulates
  directories. Do not replicate; `test_config_instance_not_mutated` guards it.
- **R8 — Optional extensions must fail soft.** A hard
  `extensions=["jinja2_time.TimeExtension", ...]` makes `Environment()` raise
  at construction when the package is missing, breaking a minimal install.
  Each optional extension is imported in its own try/except with a warning.

### External Dependencies

| Package | Version | Reason |
|---|---|---|
| `jinja2` | `>=3.1.4` (already pinned, `pyproject.toml:41`) | `ChoiceLoader`, `DictLoader`, `FileSystemBytecodeCache`, `select_autoescape` all ship in 3.1 — no bump needed |
| `jinja2-time` | *(unverified — confirm name/floor on PyPI)* | `TimeExtension` — `{% now %}` tag; optional extra |
| `jinja2-iso8601` | *(unverified — confirm name/floor on PyPI)* | ISO-8601 date handling; optional extra |
| `jinja2-humanize-extension` | *(unverified — confirm name/floor on PyPI)* | Humanized dates/sizes; optional extra |

All three go under a new `[project.optional-dependencies] templates` group and
are never imported unconditionally.

---

## 8. Worktree Strategy

- **Default isolation unit**: `per-spec`.
- All tasks run **sequentially in one worktree** — Modules 1–3 all edit
  `notify/templates.py`, so parallel execution would collide on the same file.
  Modules 4–6 depend on Module 1's behaviour, and Module 6's tests exercise
  everything.
- **Cross-feature dependencies**: none. FEAT-001 (NAV-8390 email UTF-8) is
  already merged into `main` and forward-merged into `dev` at `52cd232`; it
  touches `notify/providers/*` and `_mime_utils`, never `notify/templates.py`.

```bash
git worktree add -b feat-002-templateparser-refactor \
  .claude/worktrees/feat-002-templateparser-refactor HEAD
```

---

## 9. Open Questions

> No brainstorm document preceded this spec. The four questions below were
> asked and resolved directly with the author during `/sdd-spec`.

- [x] Should `compile_templates()` stay in `__init__`? — *Resolved by author*:
  no. Remove it; expose an opt-in `FileSystemBytecodeCache` via
  `bytecode_cache_dir=` plus an explicit `compile_directory()`. Reflected in
  §1 G4, §2 Overview point 3, §5, and §7 R3.
- [x] How should the third-party Jinja2 extensions be incorporated? —
  *Resolved by author*: declare a `templates` optional-dependency extra in
  `pyproject.toml` **and** load each extension tolerantly (try/except +
  warning), so a minimal install never breaks. Reflected in §1 G9, §3 Module 5,
  §7 R8, §7 External Dependencies.
- [x] Is the import-time `TemplateEnv` singleton in scope? — *Resolved by
  author*: yes. Make it lazily initialised and degrade an absent template
  directory to a warning instead of `RuntimeError`. Reflected in §1 G8,
  §3 Module 4, §5, and §7 R5.
- [x] Target version? — *Resolved by author*: `1.6.0` (minor — additive
  functionality, backward compatible). Reflected in the header and §5.

Remaining for implementation time:

- [ ] Confirm the exact PyPI distribution names and version floors for
  `jinja2-time`, `jinja2-iso8601` and `jinja2-humanize-extension` before
  writing them into the extra — *Owner: implementer*
- [ ] Decide whether `jinja_config` (the deprecated dict alias) should emit a
  `DeprecationWarning` on access in 1.6.0 or stay silent until 2.0.0 —
  *Owner: Jesus Lara*

---

## Revision History

| Version | Date | Author | Change |
|---|---|---|---|
| 0.1 | 2026-08-06 | Jesus Lara | Initial draft — derived from a comparative audit of `notify/templates.py` against ai-parrot `parrot/template/engine.py` |
