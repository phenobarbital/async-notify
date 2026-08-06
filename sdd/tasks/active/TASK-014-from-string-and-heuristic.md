# TASK-014: `is_template_source()` + `TemplateParser.from_string()` with bounded LRU cache

**Feature**: FEAT-003 — Inline Jinja2 template source for `send()`
**Spec**: `sdd/specs/jinja-string-notify.spec.md`
**Status**: pending
**Priority**: high
**Estimated effort**: M (2-4h)
**Depends-on**: none
**Assigned-to**: unassigned

---

## Context

This is the foundation of FEAT-003. Today a provider can only render a template
that exists as a **file on disk**, because `ProviderBase._prepare_` resolves
`template=` through `TemplateParser.get_template()`, whose loader is a
`FileSystemLoader` over a single directory (`notify/templates.py:43-45`).

This task adds the missing compile entry point — `from_string()` — plus the
detection helper that lets `template=` accept either a filename or raw Jinja2
source. It touches **only** `notify/templates.py`. The provider-side dispatch
that consumes it is TASK-015.

Implements spec §3 Module 1. See spec §2 (Overview + heuristic table) for the
design rationale and §7 R1/R2/R4/R5/R6/R10 for the risks this code must respect.

---

## Scope

- Add module-level `JINJA_MARKERS: tuple[str, ...] = ("{{", "{%", "{#")`.
- Add module-level `DEFAULT_STRING_CACHE_SIZE: int = 128`.
- Add module-level function `is_template_source(value: str) -> bool`.
- Add a module logger (`logging.getLogger("Notify.TemplateParser")`) — the
  module has **none** today.
- In `TemplateParser.__init__`, initialise the string-cache state:
  `_string_cache` (`OrderedDict`), `_string_cache_size` (from a new
  `string_cache_size` kwarg, default `DEFAULT_STRING_CACHE_SIZE`),
  `_string_cache_lock` (`threading.Lock`).
- Add `TemplateParser.from_string(self, source: str, *, cache: bool = True) -> Template`.
- Add `TemplateParser.clear_string_cache(self) -> None`.

**NOT in scope**:
- Any change to `ProviderBase._prepare_` — that is TASK-015.
- Any change to `notify/models.py` — that is TASK-016.
- Writing the test suite — that is TASK-017 (though you may run ad-hoc checks).
- Docs and the version bump — that is TASK-018.
- Touching `get_template()`, `render()`, `render_async()`, `add_filter()`,
  `environment`, or the `compile_templates()` call. **This task is purely
  additive.** In particular do NOT "fix" the `add_filter` bug at
  `notify/templates.py:94` or the `"NAV: "` prefix at `:129` — those belong to
  FEAT-002.

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `notify/templates.py` | MODIFY | Add imports, `JINJA_MARKERS`, `DEFAULT_STRING_CACHE_SIZE`, logger, `is_template_source()`, cache state in `__init__`, `from_string()`, `clear_string_cache()` |

---

## Codebase Contract (Anti-Hallucination)

> **CRITICAL**: This section contains VERIFIED code references from the actual codebase.
> The implementing agent MUST use these exact imports, class names, and method signatures.
> **DO NOT** invent, guess, or assume any import, attribute, or method not listed here.
> If you need something not listed, VERIFY it exists first with `grep` or `read`.

Verified 2026-08-06 against `dev@f42d302`.

### Verified Imports

```python
# Already present at the top of notify/templates.py
from pathlib import Path                                    # line 1
from typing import Optional                                 # line 2
from collections.abc import Callable                        # line 3
from navconfig import config                                # line 4
from jinja2 import Environment, FileSystemLoader, TemplateError, TemplateNotFound  # line 5

# NEW imports this task must add
import threading
from hashlib import sha256
from collections import OrderedDict
from jinja2 import Template, TemplateSyntaxError            # both ship in jinja2 3.1
from navconfig.logging import logging                       # repo-wide logging pattern
```

`jinja2>=3.1.4` is already a hard dependency (`pyproject.toml:41`). **No new
package and no version bump.** `hashlib`, `threading` and `collections` are stdlib.

### Existing Signatures to Use

```python
# notify/templates.py  (131 lines total, before this task)
jinja_config = {                                            # line 7
    "enable_async": True,
    "extensions": ["jinja2.ext.i18n", "jinja2.ext.loopcontrols"],
}

class TemplateParser:                                       # line 13
    def __init__(self, directory: Path, filters: Optional[list] = None, **kwargs):  # line 20
        self.template = None                                # line 26
        self.path = directory.resolve()                     # line 27
        self.filters = filters                              # line 28
        # RuntimeError if directory absent                  # lines 29-32
        # "config" kwarg shallow-merged over jinja_config   # lines 33-36
        # TEMPLATE_DEBUG appends jinja2.ext.debug           # lines 37-41
        templateLoader = FileSystemLoader(searchpath=[str(self.path)])  # lines 43-45
        self.env: Optional[Environment] = Environment(loader=templateLoader, **self.config)  # 49-51
        # self.env.compile_templates(target=..., zip="deflated")        # 53-58
        if self.filters is not None:                        # line 64
            self.env.filters.update(self.filters)           # line 65

    def get_template(self, filename: str): ...              # line 67 — DO NOT MODIFY
    @property
    def environment(self): ...                              # lines 83-85 — DO NOT MODIFY
    def add_filter(self, func, name=None) -> None: ...      # line 87 — DO NOT MODIFY
    def render(self, filename, params=None) -> str: ...     # line 99 — DO NOT MODIFY
    async def render_async(self, filename, params=None) -> str: ...  # line 112 — DO NOT MODIFY
```

`self.env` is a live `jinja2.Environment`. `Environment.from_string(source)`
returns a `jinja2.Template` — this is the stdlib-of-jinja2 API this task wraps.

**Where to put the cache init**: after the `Environment(...)` construction
(line 51) and the `try/except` that wraps it, alongside the existing
`self.filters` handling at lines 64-65. It must run for every parser instance.

**No `self.logger` exists on `TemplateParser` today** — verified via
`grep -n "logger" notify/templates.py` → no hits. Create one.

### Does NOT Exist

- ~~`TemplateParser.from_string()`~~ — this task creates it.
- ~~`TemplateParser.clear_string_cache()`~~ / ~~`TemplateParser._string_cache`~~ / ~~`_string_cache_lock`~~ / ~~`_string_cache_size`~~ — all created here.
- ~~`notify.templates.is_template_source()`~~ / ~~`JINJA_MARKERS`~~ / ~~`DEFAULT_STRING_CACHE_SIZE`~~ — all created here.
- ~~`TemplateParser.render_string()`~~ / ~~`render_string_async()`~~ — **do not use, do not create.** They do not exist. They are being added by a *different* feature, **FEAT-002** (`sdd/specs/templateparser-refactor.spec.md`, TASK-008), and they return a **rendered `str`**. This task needs the **uncalled `jinja2.Template` object**. Do not "reuse" or alias them.
- ~~`notify.templates.JinjaConfig`~~ / ~~`add_templates()`~~ / ~~`add_template_dir()`~~ / ~~`add_filters()`~~ / ~~`add_globals()`~~ / ~~`compile_directory()`~~ — all FEAT-002, none present on `dev`. Do not import or assume them.
- ~~`self.logger` on `TemplateParser`~~ — must be created by this task.
- ~~`notify/conf.py::TEMPLATE_DEBUG`~~ — not defined in `conf.py`; read ad hoc via `config.getboolean` at `notify/templates.py:37-39`.
- ~~`functools.lru_cache` on a method~~ — do NOT use it here. It keys on `self` and holds a strong reference to the parser, and it gives no `clear_string_cache()` per instance. Use the explicit `OrderedDict`.

---

## Implementation Notes

### Pattern to Follow

```python
JINJA_MARKERS: tuple[str, ...] = ("{{", "{%", "{#")
DEFAULT_STRING_CACHE_SIZE: int = 128


def is_template_source(value: str) -> bool:
    """Decide whether *value* is Jinja2 source text rather than a filename.

    Conservative by design: returns ``True`` only when *value* carries a
    signal that a template filename cannot carry — a Jinja2 delimiter
    (``{{``, ``{%``, ``{#``) or a line break. Anything else is treated as a
    filename, which preserves 1.5.7 behaviour for every existing caller.

    Args:
        value: The raw ``template=`` argument.

    Returns:
        ``True`` if *value* should be compiled as source, ``False`` if it
        should be resolved through the filesystem loader.
    """
    if not isinstance(value, str) or not value:
        return False
    if any(marker in value for marker in JINJA_MARKERS):
        return True
    return "\n" in value or "\r" in value
```

```python
    def from_string(self, source: str, *, cache: bool = True) -> Template:
        """Compile Jinja2 *source* text into a Template on this Environment.

        ... (Google-style docstring per spec §2 "New Public Interfaces") ...
        """
        if not isinstance(source, str) or not source.strip():
            raise ValueError(
                f"Notify: template source must be a non-empty string, got {source!r}"
            )
        if not cache:
            return self._compile_source(source)
        key = sha256(source.encode("utf-8")).hexdigest()
        with self._string_cache_lock:
            if key in self._string_cache:
                self._string_cache.move_to_end(key)      # LRU refresh
                return self._string_cache[key]
        template = self._compile_source(source)          # compile OUTSIDE the lock
        with self._string_cache_lock:
            self._string_cache[key] = template
            self._string_cache.move_to_end(key)
            while len(self._string_cache) > self._string_cache_size:
                evicted, _ = self._string_cache.popitem(last=False)
                self.logger.debug(f"Evicted string template {evicted[:12]} from cache")
        return template
```

Where `_compile_source` is a small private helper doing the error mapping:

```python
        try:
            return self.env.from_string(source)
        except TemplateSyntaxError as ex:
            raise ValueError(
                f"Notify: Error parsing template source at line {ex.lineno}: {ex.message}"
            ) from ex
        except Exception as err:
            raise RuntimeError(
                f"Notify: Error compiling template source: {err}"
            ) from err
```

### Key Constraints

- **`from_string()` returns a `jinja2.Template`, never a rendered `str`.** This
  is the single most important property: `ProviderBase._render_` calls
  `self._template.render_async(**args)` on it (`notify/providers/base.py:184`).
- **`from_string()` stays synchronous.** It is a compile step doing no I/O,
  exactly like `get_template()`. It is called from inside the async
  `_prepare_`, which is fine.
- **Compile outside the lock**, insert inside it. Holding a `threading.Lock`
  across Jinja2 compilation would serialise every provider in the process.
  A benign double-compile under a race is acceptable; a stalled event loop is not.
- **Error contract**: `ValueError` for bad/blank/non-`str` input and for
  `TemplateSyntaxError` (message must carry `"Notify:"` and the line number);
  `RuntimeError` for anything else. **Never raise `FileNotFoundError`** — that
  is reserved for the filesystem path, and TASK-015's dispatch relies on the
  distinction.
- Use `self.logger`, never `print` (CLAUDE.md → Code Standards).
- Google-style docstrings with strict type hints on every new function/method.
- Do not mutate the module-level `jinja_config` dict.
- Keep the module import-safe: no filesystem writes, no exceptions at import time.

### Heuristic guard rails (spec §7 R2)

A false **positive** would be a silent data-corruption bug: an existing caller
passing `"email.html"` would start rendering the literal string `"email.html"`
as the message body instead of loading the file. Keep the rules to exactly the
two above. **Do not** add HTML sniffing (`<`/`>`), length thresholds, or
extension checks without a spec revision.

### References in Codebase

- `notify/templates.py:67-81` — `get_template()`: the error-mapping style to mirror.
- `notify/templates.py:49-51` — where `self.env` is built; the cache init goes after it.
- `notify/providers/base.py:184` — the consumer that proves the return type must be `Template`.

---

## Acceptance Criteria

- [ ] `from notify.templates import is_template_source, JINJA_MARKERS, DEFAULT_STRING_CACHE_SIZE` works
- [ ] `TemplateParser(...).from_string("Hi {{ who }}")` returns a `jinja2.Template` (assert `isinstance`), **not** a `str`
- [ ] `template.render(who="x") == "Hi x"` and `await template.render_async(who="x") == "Hi x"`
- [ ] A filter registered on the parser's env is usable inside a string template (shared `Environment` proven)
- [ ] Two `from_string()` calls with identical source return the **same object**; `cache=False` returns a fresh object and does not grow the cache
- [ ] With `string_cache_size=2`, compiling 3 distinct sources leaves exactly 2 entries, evicting the least-recently-used
- [ ] Re-using the oldest entry protects it from the next eviction (`move_to_end` on hit)
- [ ] `clear_string_cache()` empties the cache
- [ ] `from_string("{% if %}")` raises `ValueError` whose message contains `"Notify:"` and a line number
- [ ] `from_string("")`, `from_string("   ")`, `from_string(123)` all raise `ValueError`
- [ ] `from_string()` never raises `FileNotFoundError`
- [ ] `is_template_source()` → `True` for `"{{ x }}"`, `"{% if x %}a{% endif %}"`, `"{# c #}"`, `"a\nb"`
- [ ] `is_template_source()` → `False` for `"email.html"`, `"welcome.txt"`, `"notifications/welcome.html"`, `"a_b-c.2.html"`, `"template"`, `""`
- [ ] No existing method in `notify/templates.py` changed behaviour — `git diff` shows only additions plus the cache-init lines in `__init__`
- [ ] No linting errors: `.venv/bin/python -m ruff check notify/templates.py`
- [ ] Existing suite still green: `.venv/bin/python -m pytest tests/ -v`

---

## Test Specification

> Formal tests land in TASK-017. Use this scaffold to self-verify before handing off.

```python
import pytest
from pathlib import Path
from jinja2 import Template
from notify.templates import TemplateParser, is_template_source


@pytest.fixture
def parser(tmp_path):
    d = tmp_path / "templates"
    d.mkdir()
    (d / "hello.html").write_text("Hi {{ who }}", encoding="utf-8")
    return TemplateParser(directory=d)


class TestIsTemplateSource:
    @pytest.mark.parametrize("value", ["{{ x }}", "{% if x %}a{% endif %}", "{# c #}", "a\nb"])
    def test_detects_source(self, value):
        assert is_template_source(value) is True

    @pytest.mark.parametrize(
        "value",
        ["email.html", "welcome.txt", "notifications/welcome.html", "a_b-c.2.html", "template", ""],
    )
    def test_rejects_filenames(self, value):
        """G4 guard — a false positive here is a silent data-corruption bug."""
        assert is_template_source(value) is False


class TestFromString:
    def test_returns_template_object(self, parser):
        assert isinstance(parser.from_string("Hi {{ who }}"), Template)

    def test_renders_sync_and_async(self, parser):
        assert parser.from_string("Hi {{ who }}").render(who="x") == "Hi x"

    def test_cache_hit_same_object(self, parser):
        assert parser.from_string("{{ a }}") is parser.from_string("{{ a }}")

    def test_cache_disabled(self, parser):
        a = parser.from_string("{{ a }}", cache=False)
        b = parser.from_string("{{ a }}", cache=False)
        assert a is not b

    def test_cache_evicts_lru(self, tmp_path):
        d = tmp_path / "t"; d.mkdir()
        p = TemplateParser(directory=d, string_cache_size=2)
        p.from_string("{{ a }}"); p.from_string("{{ b }}"); p.from_string("{{ c }}")
        assert len(p._string_cache) == 2

    def test_syntax_error_raises_valueerror(self, parser):
        with pytest.raises(ValueError, match="Notify:"):
            parser.from_string("{% if %}")

    def test_never_raises_filenotfound(self, parser):
        assert isinstance(parser.from_string("{{ x }}/y.html"), Template)
```

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** at `sdd/specs/jinja-string-notify.spec.md` — especially §2, §3 Module 1, §7.
2. **Check dependencies** — none.
3. **Verify the Codebase Contract** before writing ANY code:
   - Confirm `notify/templates.py` line numbers still match (FEAT-002 may have
     landed first and rewritten this file — if so, adapt: `from_string()` only
     needs `self.env` to exist, and **must not** be re-expressed in terms of
     FEAT-002's `render_string()`).
   - **NEVER** reference an import, attribute, or method not in the contract
     without verifying it exists.
4. **Update status** in `sdd/tasks/index/jinja-string-notify.json` → `"in-progress"`.
5. **Implement** following the scope, contract, and notes above.
6. **Verify** every acceptance criterion.
7. **Move this file** to `sdd/tasks/completed/TASK-014-from-string-and-heuristic.md`.
8. **Update index** → `"done"`.
9. **Fill in the Completion Note** below.

---

## Completion Note

*(Agent fills this in when done)*

**Completed by**: <session or agent ID>
**Date**: YYYY-MM-DD
**Notes**: What was implemented, any deviations from scope, issues encountered.

**Deviations from spec**: none | describe if any
