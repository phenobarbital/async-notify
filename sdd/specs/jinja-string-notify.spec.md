---
# FEAT-145 flow-type fields.
# Feature work bases on dev — no production hotfix involved.
type: feature
base_branch: dev
---

# Feature Specification: Inline Jinja2 template source for `send()`

**Feature ID**: FEAT-003
**Date**: 2026-08-06
**Author**: Jesus Lara
**Status**: approved
**Target version**: 1.6.0

---

## 1. Motivation & Business Requirements

### Problem Statement

Every async-notify provider can render a Jinja2 template, but only ever one
that already exists **as a file on disk**. `ProviderBase._prepare_` resolves
the `template` keyword through the filesystem-backed parser:

```python
# notify/providers/base.py:140-144
if template:
    # Getting Template from Template Parser.
    self._template = self._tpl.get_template(template)
else:
    self._template = None
```

`TemplateParser.get_template()` (`notify/templates.py:67-81`) delegates to
`Environment.get_template()`, whose loader is a `FileSystemLoader` built from
exactly one directory (`notify/templates.py:43-45`). There is no supported way
to hand a provider the template **body** instead of its filename.

That blocks a family of legitimate callers:

1. **Templates stored outside the filesystem** — per-tenant bodies in Postgres,
   a CMS, or S3. Today the caller must materialise a temp file inside
   `TEMPLATE_DIR` before every send.
2. **Templates composed at runtime** — a body assembled from a subject plus a
   fragment, or a caller-supplied snippet in an API request payload.
3. **Callers of the Notify Server** — `notify/server/wrapper.py:70-78` forwards
   `**self.kwargs` straight into `client.send()`, so an enqueued notification
   can carry a `template` filename over Redis but never the body it refers to.
   The worker and the enqueuing process must therefore share a filesystem.
4. **Tests and examples** — every offline test that wants to exercise the
   render path has to create a directory of fixture files first.

The plumbing to fix this is already almost entirely in place, and this is what
makes the feature cheap: `_prepare_` is defined **exactly once** in the whole
package (`notify/providers/base.py:116` — verified, no provider overrides it),
and all eight render call sites operate on the `jinja2.Template` **object** that
`_prepare_` stored in `self._template`, never on `TemplateParser` itself. A
single dispatch change in `_prepare_`, plus one new method on `TemplateParser`,
therefore reaches every provider — SMTP, Gmail, Office365, Outlook, SES, mail,
Telegram, Slack, Teams, Twilio — with no per-provider edits at all.

### Goals

- **G1** — `TemplateParser.from_string(source)` compiles Jinja2 source text into
  a `jinja2.Template`, using the same `Environment` (and therefore the same
  filters, globals, extensions and `enable_async` setting) as file templates.
- **G2** — `send(..., template=<jinja source>)` works on **every** provider that
  routes through `ProviderBase._prepare_`, with no provider-level changes.
- **G3** — `template=` transparently accepts **either** a template filename
  (today's meaning) **or** raw Jinja2 source, discriminated by a deterministic
  heuristic. No new keyword is required of the caller.
- **G4** — Existing callers passing a filename keep byte-identical behaviour.
  The heuristic must never reclassify a realistic template filename as source.
- **G5** — Compiled string templates are cached in a bounded LRU keyed by a
  hash of the source, so re-sending the same body (per recipient, or in a loop)
  does not recompile.
- **G6** — An explicit escape hatch, `template_is_source=`, lets a caller force
  either interpretation when the heuristic cannot decide.
- **G7** — Works unchanged through the Notify Server path, since
  `NotifyWrapper` already forwards arbitrary kwargs to `send()`.
- **G8** — `notify/models.py::Message.template` widens from `Path` to
  `Union[Path, str]` so the model can carry inline source as well as a
  filename, keeping it consistent with the new `send()` semantics
  (§9 Q5, resolved by the author at approval time).

### Non-Goals (explicitly out of scope)

- **A separate `template_string=` keyword.** Overloading `template=` was chosen
  deliberately over a second keyword (§9 Q1). `template_string` must NOT be
  introduced.
- **Wiring `Message` / `BlockMessage` / `MailMessage` into the send path.**
  G8 widens the `template` *field type* only. Those models have **no consumers
  inside `notify/`** (verified — see §6), and this spec does not change that.
  `send()` keeps taking `template=` as a plain keyword.
- **Fixing OneSignal.** `Onesignal.send()` (`notify/providers/onesignal/onesignal.py:93`)
  overrides `send()` without ever calling `_prepare_`, so templates — file *or*
  string — do not work there today and will not after this feature. Documented
  in §7 R7, not fixed here.
- **Turning on `autoescape`.** It is `False` today and stays `False`; see §7 R10
  for the security consequence that follows for string templates.
- **Anything in FEAT-002 (`templateparser-refactor`).** That spec independently
  rewrites `notify/templates.py` (adding `JinjaConfig`, multi-directory loaders,
  `render_string()`, `add_templates()`). This spec was scoped to be
  **independent** of it (§9 Q2) and builds on `notify/templates.py` as it stands
  at 1.5.7. Note that FEAT-002's `render_string()` returns a **rendered string**
  and cannot serve this feature, which needs the uncalled `jinja2.Template`
  object. See §7 R3 for the merge-order hazard.
- **The sync-render-inside-a-running-loop hazard** at `notify/providers/base.py:164`
  and `notify/providers/smtp/smtp.py:189` — pre-existing, unchanged, out of scope.

---

## 2. Architectural Design

### Overview

Two small additions carry the whole feature.

**1. `TemplateParser.from_string()` — a new compile entry point.**
It calls `Environment.from_string(source)` on the *existing* environment, so a
string template sees exactly the same filters, globals, extensions and
`enable_async=True` as a file template. Results are memoised in a bounded LRU
keyed by `sha256(source)`, guarded by a `threading.Lock` because `TemplateEnv`
is a process-wide singleton shared by every provider instance.

Crucially it returns the **uncompiled-to-output `jinja2.Template` object**, not
a rendered string — that is what `self._template` must hold for
`_render_`/`_render_sync_` to keep working untouched.

**2. `ProviderBase._prepare_` — a three-way dispatch.**
The single `if template:` branch at `base.py:140-144` becomes:

```
template given?
├── no  → self._template = None                      (unchanged)
└── yes → template_is_source?
          ├── True   → self._tpl.from_string(template)
          ├── False  → self._tpl.get_template(template)     (1.5.7 semantics)
          └── None   → is_template_source(template)
                       ├── True  → self._tpl.from_string(template)
                       └── False → self._tpl.get_template(template)
```

Everything downstream is untouched: `self._template` is a `jinja2.Template`
either way, so the eight `render()` / `render_async()` call sites listed in §6
keep working verbatim.

**The heuristic** (`notify/templates.py::is_template_source`) is intentionally
conservative and biased toward the legacy interpretation. Source is declared
only when the value carries a signal a real template filename cannot carry:

| Signal | Rationale |
|---|---|
| contains `{{`, `{%` or `{#` | Jinja2 delimiters. A filename containing a brace is not a thing in this codebase, and `TEMPLATE_DIR` is a curated directory. |
| contains `\n` or `\r` | A filename is never multi-line. |

Anything else — `"email.html"`, `"notifications/welcome.txt"` — falls through to
`get_template()`, so **every existing caller is unaffected by construction**.

The residual hole is a template body that is pure literal text with no Jinja
markup and no newline (`template="Hello world"`), which is indistinguishable
from a filename and will be looked up on disk, raising `FileNotFoundError`.
That case is exactly what `template_is_source=True` exists for. It is called out
as §7 R1 rather than papered over with a fuzzier heuristic, because widening the
rules is what would put the G4 guarantee at risk.

### Component Diagram

```
caller
  └─ Notify("smtp", ...).send(recipient=…, subject=…,
                              template=<filename | jinja source>,
                              template_is_source=None|True|False, **params)
          │
          ▼
   ProviderBase.send()                          notify/providers/base.py:242
   Mail.send()                                  notify/providers/mail.py:209
   Ses.send()                                   notify/providers/ses/ses.py:158
     (all three forward **kwargs unchanged)
          │
          ▼
   ProviderBase._prepare_(template=…, template_is_source=…)      base.py:116
          │                      ↑ the ONLY definition in the package
          │
          ├── template_is_source is False ──┐
          ├── heuristic says "filename"  ───┤
          │                                 ▼
          │                    TemplateParser.get_template(name)   templates.py:67
          │                                 │  FileSystemLoader
          │                                 ▼
          ├── template_is_source is True  ──┐
          └── heuristic says "source"    ───┤
                                            ▼
                            TemplateParser.from_string(source)     NEW
                              ├─ sha256(source) → _string_cache (LRU, locked)
                              └─ env.from_string(source)
                                            │
                                            ▼
                                   jinja2.Template  ──▶ self._template
                                            │
        ┌───────────────────────────────────┴───────────────────────────────┐
        ▼                                                                   ▼
  _render_sync_()  base.py:164                              _render_()  base.py:184
  smtp.py:189                                    mail.py:152 · ses.py:104 · gmail.py:84
                                                 outlook.py:146 · office365.py:166
                             (ALL EIGHT UNCHANGED — they call the Template object)
```

### Integration Points

| Existing Component | Integration Type | Notes |
|---|---|---|
| `notify/templates.py::TemplateParser` | **extends** | Adds `from_string()`, `clear_string_cache()`, module-level `is_template_source()`. No existing method changes. |
| `notify/providers/base.py::ProviderBase._prepare_` | **modifies** | `base.py:140-144` dispatch replaced; new `template_is_source` parameter. The only definition of `_prepare_` in the package. |
| `notify/providers/base.py::ProviderBase._render_` / `_render_sync_` | **unchanged** | Operate on `self._template`; agnostic to its origin. |
| `notify/providers/mail.py::Mail.send` | **unchanged** | Calls `_prepare_(**kwargs)` at `mail.py:232` — inherits the feature. |
| `notify/providers/ses/ses.py::Ses.send` | **unchanged** | Calls `_prepare_(**kwargs)` at `ses.py:171` — inherits the feature. |
| `notify/providers/onesignal/onesignal.py::Onesignal.send` | **unchanged (still unsupported)** | Never calls `_prepare_`; see §7 R7. |
| `notify/server/wrapper.py::NotifyWrapper` | **unchanged** | Already forwards `**self.kwargs` into `send()` (`wrapper.py:70-78`); string templates traverse the Redis path with no change. |
| `notify/notify.py::TemplateEnv` | **unchanged** | Still the process-wide singleton; now also owns the string cache. |
| `notify/models.py::Message.template` | **widens** | `Path` → `Union[Path, str]` (G8). Inherited by `BlockMessage` and `MailMessage`. No consumers inside `notify/` — see §6. |

### Data Models

No Pydantic/datamodel model changes. The only new structured state is the
parser-local cache:

```python
# notify/templates.py

#: Jinja2 delimiters that can never appear in a template *filename*.
JINJA_MARKERS: tuple[str, ...] = ("{{", "{%", "{#")

#: Default upper bound on the number of compiled string templates retained.
DEFAULT_STRING_CACHE_SIZE: int = 128


class TemplateParser:
    # new instance state, initialised in __init__
    _string_cache: "OrderedDict[str, Template]"
    _string_cache_size: int          # from kwargs, default DEFAULT_STRING_CACHE_SIZE
    _string_cache_lock: threading.Lock
```

### New Public Interfaces

```python
# notify/templates.py

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


class TemplateParser:
    def from_string(self, source: str, *, cache: bool = True) -> "Template":
        """Compile Jinja2 *source* text into a Template on this Environment.

        The returned template shares the parser's filters, globals,
        extensions and ``enable_async`` setting, so it renders identically
        to an equivalent on-disk template.

        Args:
            source: Jinja2 template source text.
            cache: When ``True`` (default), memoise the compiled template in
                a bounded LRU keyed by the SHA-256 of *source*.

        Returns:
            A compiled :class:`jinja2.Template`.

        Raises:
            ValueError: If *source* is empty/blank, is not a ``str``, or
                fails to parse (``jinja2.TemplateSyntaxError``). The message
                carries the offending line number.
            RuntimeError: On any other compilation failure.
        """

    def clear_string_cache(self) -> None:
        """Drop every compiled string template from the LRU cache."""


# notify/providers/base.py

class ProviderBase(ABC):
    async def _prepare_(
        self,
        recipient: Actor = None,
        message: Union[str, Any] = None,
        template: Optional[str] = None,
        template_is_source: Optional[bool] = None,
        **kwargs,
    ):
        """Prepare a Message for Sending.

        Args:
            recipient: Target Actor (used for ``format_map`` interpolation).
            message: Raw message body.
            template: Either a template **filename** resolved through
                ``TEMPLATE_DIR``, or raw Jinja2 **source text**. The two are
                discriminated by :func:`notify.templates.is_template_source`
                unless *template_is_source* forces the choice.
            template_is_source: ``None`` (default) auto-detects; ``True``
                forces *template* to be compiled as source; ``False`` forces
                filesystem resolution, i.e. exact 1.5.7 semantics.
        """
```

Caller-facing usage, identical across every provider:

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

---

## 3. Module Breakdown

### Module 1: `is_template_source()` + `TemplateParser.from_string()`
- **Path**: `notify/templates.py`
- **Responsibility**: Module-level `JINJA_MARKERS`, `DEFAULT_STRING_CACHE_SIZE`
  and `is_template_source()`. On `TemplateParser`: initialise
  `_string_cache` / `_string_cache_size` / `_string_cache_lock` in `__init__`
  (accepting a `string_cache_size` kwarg), implement `from_string()` with
  SHA-256-keyed bounded LRU + lock, and `clear_string_cache()`. Add a
  `self.logger` (the module has none today) for the eviction/debug path.
- **Depends on**: nothing new inside the repo. `jinja2.Template` and
  `TemplateSyntaxError` come from the already-pinned `jinja2>=3.1.4`.

### Module 2: `_prepare_` dispatch
- **Path**: `notify/providers/base.py`
- **Responsibility**: Add the `template_is_source: Optional[bool] = None`
  parameter to `_prepare_` (`base.py:116-122`) and replace the
  `if template:` block (`base.py:140-144`) with the three-way dispatch from §2.
  No other method in the file changes.
- **Depends on**: Module 1.

### Module 3: Widen `Message.template`
- **Path**: `notify/models.py`
- **Responsibility**: Change `template: Path` (`notify/models.py:93`) to
  `template: Union[Path, str]`, so `Message` (and its subclasses
  `BlockMessage`, `MailMessage`) can carry inline Jinja source. `Union` is
  already imported at `notify/models.py:3`; `Path` at `:4`. No other line in
  the file changes.
- **Depends on**: nothing. Shares no file with any other module in this spec.

### Module 4: Test suite
- **Path**: `tests/test_jinja_string_templates.py`
- **Responsibility**: The offline suite in §4. Includes a concrete
  `ProviderBase` subclass fixture that records what `_prepare_` produced, so the
  provider-agnostic claim (G2) is actually asserted rather than assumed.
- **Depends on**: Modules 1–3.

### Module 5: Documentation + version bump
- **Path**: `docs/api.rst`, `docs/providers.rst`, `README.md`, `notify/version.py`
- **Responsibility**: Document the overloaded `template=` argument, the
  detection rules, `template_is_source=`, the cache and its `string_cache_size`
  knob, the widened `Message.template`, and the §7 R10 security note about
  untrusted template source. Bump `__version__` to `1.6.0`.
- **Depends on**: Modules 1–3.

---

## 4. Test Specification

All tests are offline — no network, no SMTP, no external services. Template
directories are built with `tmp_path`.

### Unit Tests

| Test | Module | Description |
|---|---|---|
| `test_is_template_source_detects_variable` | 1 | `"{{ x }}"` → `True`. |
| `test_is_template_source_detects_block` | 1 | `"{% if x %}a{% endif %}"` → `True`. |
| `test_is_template_source_detects_comment` | 1 | `"{# note #}"` → `True`. |
| `test_is_template_source_detects_newline` | 1 | `"line one\nline two"` → `True`. |
| `test_is_template_source_rejects_plain_filenames` | 1 | **G4 guard.** Parametrised over `"email.html"`, `"welcome.txt"`, `"notifications/welcome.html"`, `"a_b-c.2.html"`, `"template"` → all `False`. |
| `test_is_template_source_rejects_empty` | 1 | `""` → `False`. |
| `test_from_string_returns_template_object` | 1 | Returns a `jinja2.Template`, **not** a `str` — guards the FEAT-002 `render_string()` confusion (§7 R3). |
| `test_from_string_renders_sync_and_async` | 1 | `render(who="x")` and `await render_async(who="x")` both produce `"Hi x"`. |
| `test_from_string_shares_environment_filters` | 1 | A filter registered via `add_filter`/`env.filters` is usable inside a string template. |
| `test_from_string_shares_environment_globals` | 1 | An `env.globals` entry is visible to a string template. |
| `test_from_string_cache_hit_returns_same_object` | 1 | Two calls with identical source return the *same* `Template` instance. |
| `test_from_string_cache_miss_on_different_source` | 1 | Different source → different object. |
| `test_from_string_cache_disabled` | 1 | `cache=False` returns a fresh object each call and does not grow the cache. |
| `test_from_string_cache_evicts_lru` | 1 | With `string_cache_size=2`, compiling three distinct sources leaves 2 entries and evicts the least-recently-used. |
| `test_from_string_cache_reuse_refreshes_lru_order` | 1 | Re-using the oldest entry protects it from the next eviction. |
| `test_clear_string_cache` | 1 | Empties the cache; a subsequent compile yields a new object. |
| `test_from_string_syntax_error_raises_valueerror` | 1 | `"{% if %}"` raises `ValueError`, message contains `"Notify:"` and a line number. |
| `test_from_string_empty_raises_valueerror` | 1 | `""` and `"   "` raise `ValueError`. |
| `test_from_string_non_str_raises_valueerror` | 1 | `from_string(123)` raises `ValueError`, never `TypeError` from deep inside Jinja2. |
| `test_from_string_never_raises_filenotfound` | 1 | A source string that happens to look path-like still compiles; `FileNotFoundError` is reserved for the filesystem path. |
| `test_prepare_with_source_sets_template` | 2 | `_prepare_(template="{{ who }}")` sets `self._template` to a compiled template; `get_template` is never called (patched + asserted). |
| `test_prepare_with_filename_unchanged` | 2 | **G4 guard.** `_prepare_(template="hello.html")` routes to `get_template("hello.html")` exactly as in 1.5.7. |
| `test_prepare_without_template_sets_none` | 2 | No `template` → `self._template is None` (unchanged). |
| `test_prepare_empty_template_sets_none` | 2 | `template=""` is falsy → `self._template is None` (unchanged). |
| `test_prepare_force_source_true` | 2 | `template="Hello world", template_is_source=True` compiles as source instead of hitting the filesystem. |
| `test_prepare_force_source_false` | 2 | `template="{{ x }}", template_is_source=False` routes to `get_template()` and raises `FileNotFoundError`. |
| `test_prepare_missing_file_still_raises_filenotfound` | 2 | A filename-shaped value that does not exist keeps raising `FileNotFoundError`. |
| `test_prepare_source_syntax_error_propagates` | 2 | Bad source surfaces the `ValueError` from Module 1 rather than a `FileNotFoundError`. |
| `test_message_template_accepts_path` | 3 | `Message(name="x", template=Path("a.html"))` still constructs — regression guard for the widening. |
| `test_message_template_accepts_str` | 3 | `Message(name="x", template="{{ who }}")` constructs and round-trips the string unchanged (not coerced to `Path`). |
| `test_blockmessage_inherits_widened_template` | 3 | `BlockMessage` accepts a `str` template, proving the widening is inherited. |

### Integration Tests

| Test | Description |
|---|---|
| `test_render_async_with_string_template` | A concrete `ProviderBase` subclass sends with `template="<b>{{ message }}</b>"`; `_render_()` returns the rendered HTML — proves the provider-agnostic claim (G2) end to end. |
| `test_render_sync_with_string_template` | Same through `_render_sync_()` (the `smtp.py:189` path). |
| `test_string_and_file_template_render_identically` | The same body, once on disk and once inline, produces byte-identical output. |
| `test_send_forwards_template_is_source_kwarg` | `send(..., template=…, template_is_source=True)` reaches `_prepare_` through `**kwargs` on the base `send()`. |
| `test_mail_send_path_forwards_kwargs` | `Mail.send`'s own `_prepare_` call (`mail.py:232`) forwards the new kwargs (transport mocked). |
| `test_ses_send_path_forwards_kwargs` | Same for `Ses.send` (`ses.py:171`), transport mocked. |
| `test_template_env_singleton_cache_shared` | Two provider instances compiling identical source share one cached `Template` via the `TemplateEnv` singleton. |

### Test Data / Fixtures

```python
@pytest.fixture
def template_dir(tmp_path):
    """Minimal on-disk template set."""
    d = tmp_path / "templates"
    d.mkdir()
    (d / "hello.html").write_text("Hi {{ who }}", encoding="utf-8")
    return d


@pytest.fixture
def parser(template_dir):
    from notify.templates import TemplateParser
    return TemplateParser(directory=template_dir)


@pytest.fixture
def dummy_provider(parser, monkeypatch):
    """Concrete ProviderBase subclass wired to a tmp-dir parser.

    Proves the feature is provider-agnostic: nothing below ProviderBase is
    involved in the render path.
    """
    from notify.providers.base import ProviderBase, ProviderType

    class Dummy(ProviderBase):
        provider = "dummy"
        provider_type = ProviderType.NOTIFY
        blocking = False

        async def connect(self, *args, **kwargs): ...
        async def close(self): ...
        async def _send_(self, to, message, subject=None, **kwargs):
            return await self._render_(to, message, subject, **kwargs)

    p = Dummy()
    p._tpl = parser          # bypass the module-level TemplateEnv singleton
    return p
```

---

## 5. Acceptance Criteria

> This feature is complete when ALL of the following are true:

- [ ] All new tests pass (`.venv/bin/python -m pytest tests/test_jinja_string_templates.py -v`)
- [ ] The pre-existing suite still passes (`.venv/bin/python -m pytest tests/ -v`) with no new failures versus the 1.5.7 baseline
- [ ] `TemplateParser.from_string(source)` returns a `jinja2.Template` **object** (never a rendered `str`), compiled on the parser's own `Environment`
- [ ] A string template sees the same filters, globals, extensions and `enable_async` setting as a file template
- [ ] `send(..., template=<jinja source>)` renders correctly on a concrete `ProviderBase` subclass through **both** `_render_()` and `_render_sync_()`
- [ ] The same body rendered from disk and from a string produces byte-identical output
- [ ] `send(..., template="email.html")` behaves exactly as in 1.5.7 — routed to `get_template()`, `FileNotFoundError` when absent
- [ ] `is_template_source()` returns `False` for every filename in the parametrised list of §4 and `True` for `{{`, `{%`, `{#` and newline-bearing input
- [ ] `template_is_source=True` forces source compilation; `template_is_source=False` forces filesystem resolution; `None` auto-detects
- [ ] `template=None` and `template=""` still yield `self._template is None`
- [ ] Compiling identical source twice returns the same cached `Template` instance; `cache=False` bypasses the cache
- [ ] The cache is bounded: with `string_cache_size=N`, compiling `N+1` distinct sources leaves exactly `N` entries and evicts the least-recently-used
- [ ] `clear_string_cache()` empties the cache
- [ ] Cache mutation is guarded by a lock (the parser is a process-wide singleton reachable from `blocking='executor'` and thread-based providers)
- [ ] Malformed source raises `ValueError` carrying `"Notify:"` and the offending line number — never `FileNotFoundError`, never a bare `jinja2.TemplateSyntaxError`
- [ ] `from_string()` rejects empty/blank/non-`str` input with `ValueError`
- [ ] **No provider file under `notify/providers/*/` is modified** — the diff touches only `notify/templates.py`, `notify/providers/base.py`, `notify/models.py`, `notify/version.py`, `tests/`, `docs/` and `README.md`
- [ ] `_prepare_` remains the single definition in the package (no provider override introduced)
- [ ] `notify/models.py::Message.template` is `Union[Path, str]` and accepts both a `Path` and a `str`; `BlockMessage` inherits the widening; no other line of `notify/models.py` changes
- [ ] `docs/` and `README.md` document the overloaded `template=`, the detection rules, `template_is_source=`, `string_cache_size`, the widened `Message.template` and the §7 R10 security note
- [ ] `notify/version.py` is bumped to `1.6.0`
- [ ] No breaking changes to the existing public API
- [ ] Google-style docstrings with strict type hints on every new/changed function and method

---

## 6. Codebase Contract

> **CRITICAL — Anti-Hallucination Anchor**
> This section is the single source of truth for what exists in the codebase.
> Implementation agents MUST NOT reference imports, attributes, or methods
> not listed here without first verifying they exist via `grep` or `read`.

All line numbers verified 2026-08-06 against the working tree at `dev@477544e`.

### Verified Imports

```python
from notify.templates import TemplateParser, jinja_config   # notify/templates.py:13, :7
from notify.conf import TEMPLATE_DIR                        # notify/conf.py
from notify.notify import Notify, TemplateEnv, LoadProvider # notify/notify.py:12, :10, :64
from notify.providers.base import ProviderBase, ProviderType # notify/providers/base.py
from notify.models import Actor                             # notify/models.py

# Third-party — jinja2 is already a hard dependency (pyproject.toml:41 → "jinja2>=3.1.4")
from jinja2 import Environment, FileSystemLoader, TemplateError, TemplateNotFound  # in use, templates.py:5
from jinja2 import Template, TemplateSyntaxError            # NEW usage; both ship in jinja2 3.1

# stdlib, new to notify/templates.py
import threading
from hashlib import sha256
from collections import OrderedDict

from navconfig import config                                # notify/templates.py:4
from navconfig.logging import logging                       # pattern used across the repo
```

### Existing Class Signatures

```python
# notify/templates.py  (131 lines total)
jinja_config = {                                            # line 7
    "enable_async": True,
    "extensions": ["jinja2.ext.i18n", "jinja2.ext.loopcontrols"],
}

class TemplateParser:                                       # line 13
    def __init__(self, directory: Path, filters: Optional[list] = None, **kwargs):  # line 20
        self.template = None                                # line 26
        self.path = directory.resolve()                     # line 27  ← Path-only today
        self.filters = filters                              # line 28
        # RuntimeError if the directory is absent            # lines 29-32
        # "config" kwarg shallow-merged over jinja_config    # lines 33-36
        # TEMPLATE_DEBUG appends jinja2.ext.debug            # lines 37-41
        # FileSystemLoader(searchpath=[str(self.path)])      # lines 43-45
        self.env: Optional[Environment] = Environment(loader=templateLoader, **self.config)  # 49-51
        # env.compile_templates(target=<path>/".compiled", zip="deflated")           # 53-58
        # env.filters.update(self.filters) when filters is not None                  # 64-65
        # NOTE: there is NO self.logger in this module today — Module 1 adds one.

    def get_template(self, filename: str): ...              # line 67
        # self.env.get_template(str(filename))              # line 72
        # TemplateNotFound → FileNotFoundError              # lines 74-77
        # any other Exception → RuntimeError                # lines 78-81
    @property
    def environment(self): ...                              # lines 83-85
    def add_filter(self, func: Callable, name: Optional[str] = None) -> None: ...  # line 87
    def render(self, filename: str, params: Optional[dict] = None) -> str: ...     # line 99  (SYNC)
    async def render_async(self, filename: str, params: Optional[dict] = None) -> str: ...  # line 112
```

```python
# notify/providers/base.py
class ProviderType(Enum):                        # NOTIFY | SMS | EMAIL | PUSH | IM

class ProviderBase(ABC):
    provider: str = None
    provider_type: ProviderType = ProviderType.NOTIFY
    blocking: bool = True
    sent: Optional[Union[Callable, Awaitable]] = None

    def __init__(self, *args, **kwargs):
        from notify.notify import TemplateEnv     # line 66 (inside a try-block)
        self._tpl = TemplateEnv                   # line 67
        self._template = None                     # line 68
        # RuntimeError("Notify: Can't load the Jinja2 Template Parser: …")  # lines 70-72
        self.sent = kwargs.pop('sent', None)      # line 74
        for arg, val in kwargs.items():           # lines 76-80
            object.__setattr__(self, arg, val)    # ← every send-kwarg name is ALSO
                                                  #   settable as a constructor attribute

    async def _prepare_(                          # line 116 ← THE ONLY DEFINITION
        self,
        recipient: Actor = None,                  # line 118
        message: Union[str, Any] = None,          # line 119
        template: str = None,                     # line 120  ← widened by this spec
        **kwargs,                                 # line 121
    ):
        # message.format_map(SafeDict(...))       # lines 128-139 (unchanged)
        if template:                              # line 140  ← REPLACED by this spec
            self._template = self._tpl.get_template(template)   # line 142
        else:
            self._template = None                 # line 144
        return msg                                # line 145

    def _render_sync_(self, to=None, message=None, subject=None, **kwargs):  # line 147
        msg = self._template.render(**self._templateargs)        # line 164

    async def _render_(self, to=None, message=None, subject=None, **kwargs): # line 167
        msg = await self._template.render_async(**self._templateargs)        # line 184

    async def send(self, recipient=None, message=None, subject=None, **kwargs):  # line 242
        message = await self._prepare_(recipient=recipient, message=message, **kwargs)  # 255-259
        # then dispatches on self.blocking: 'asyncio' | 'executor' | else ThreadMessage
        # NOTE: the SAME kwargs dict is also forwarded to _send_(…, **kwargs)
```

```python
# notify/notify.py
PROVIDERS = {}                                              # line 9
TemplateEnv = None                                          # line 10
class Notify: ...                                           # line 12
def LoadProvider(provider: str): ...                        # line 64
if __name__ == "notify.notify":                             # line 83
    TemplateEnv = TemplateParser(directory=TEMPLATE_DIR)    # lines 85-87
```

```python
# notify/server/wrapper.py
class NotifyWrapper:
    async def call(self):                                   # line 68
        notify = Notify(self._provider, **self.kwargs)
        async with notify as client:
            return await client.send(recipient=self.recipients, *self.args[1:], **self.kwargs)  # 70-78
    # ← already forwards arbitrary kwargs; string templates need NO server change
```

```python
# notify/models.py
from typing import Any, List, Union, Optional, Literal      # line 3  ← Union already imported
from pathlib import Path                                    # line 4  ← Path already imported
from datamodel import BaseModel, Column, Field              # line 9

class Message(BaseModel):                                   # line 80
    name: str = Field(required=True, default=auto_uuid)     # line 89
    body: Union[str, dict] = Field(default=None)            # line 90
    content: str = Field(required=False, default="")        # line 91
    sent: datetime = Field(required=False, default=now)     # line 92
    template: Path                                          # line 93  ← WIDENED to Union[Path, str] (G8)

class BlockMessage(Message): ...                            # line 108 — inherits `template`
class MailMessage(BlockMessage): ...                        # line 137 — inherits `template`
```

**`notify.models.Message` has NO consumers inside `notify/`.** Verified via
`grep -rn "Message" notify/ --include=*.py`: the only two `Message(` call sites
in the package import the name from **third-party** libraries, not from
`notify.models` —

| File | Line | Import source |
|---|---|---|
| `notify/providers/office365/office365.py` | 13 | `from O365 import (…, Message, …)` |
| `notify/providers/gmail/gmail.py` | 10 | `from gmail import GMail as GMailWorker, Message` |

This is why widening the field type is contained: nothing inside the package
constructs or reads `notify.models.Message.template`.

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

All eight are calls on the **`jinja2.Template` object** held in `self._template`,
never on `TemplateParser`. This is precisely why no provider needs editing.
(`notify/providers/smtp/smtp.py:151` also matches the grep but is a docstring.)

### `send()` overrides — which inherit the feature

Verified via `grep -rn '    async def send(' notify/`:

| File | Line | Calls `_prepare_`? | Effect |
|---|---|---|---|
| `notify/providers/base.py` | 242 | yes, line 255 | inherits |
| `notify/providers/mail.py` | 209 | yes, line 232 | inherits |
| `notify/providers/ses/ses.py` | 158 | yes, line 171 | inherits |
| `notify/providers/onesignal/onesignal.py` | 93 | **no** | templates unsupported there today and after — §7 R7 |
| `notify/server/client.py` | 130 | n/a — client-side enqueue, not a provider | unaffected |

### Integration Points

| New Component | Connects To | Via | Verified At |
|---|---|---|---|
| `is_template_source()` | `ProviderBase._prepare_` | function call in the new dispatch | `notify/providers/base.py:140` (block being replaced) |
| `TemplateParser.from_string()` | `ProviderBase._prepare_` | `self._tpl.from_string(template)` | `notify/providers/base.py:142` (sibling of `get_template`) |
| `_string_cache` | `TemplateParser.__init__` | instance attribute | `notify/templates.py:20-65` |
| `template_is_source` kwarg | `ProviderBase.send()` → `_prepare_` | `**kwargs` forwarding | `notify/providers/base.py:255-259` |
| `template_is_source` kwarg | `Mail.send()` / `Ses.send()` → `_prepare_` | `**kwargs` forwarding | `notify/providers/mail.py:232`, `notify/providers/ses/ses.py:171` |
| `template_is_source` kwarg | `NotifyWrapper` → `send()` | `**self.kwargs` forwarding | `notify/server/wrapper.py:70-78` |

### Does NOT Exist (Anti-Hallucination)

- ~~`TemplateParser.from_string()`~~ — added by this spec; absent in 1.5.7.
- ~~`TemplateParser.clear_string_cache()`~~ / ~~`TemplateParser._string_cache`~~ — new here.
- ~~`notify.templates.is_template_source()`~~ / ~~`JINJA_MARKERS`~~ / ~~`DEFAULT_STRING_CACHE_SIZE`~~ — new here.
- ~~`TemplateParser.render_string()`~~ / ~~`render_string_async()`~~ — **do not use.** They do not exist in 1.5.7. They are being added by **FEAT-002** (`sdd/specs/templateparser-refactor.spec.md`), they return a **rendered `str`**, and they therefore CANNOT implement this feature, which needs the uncalled `jinja2.Template` object. Do not "reuse" them.
- ~~`notify.templates.JinjaConfig`~~ / ~~`add_templates()`~~ / ~~`add_template_dir()`~~ / ~~`add_filters()`~~ / ~~`add_globals()`~~ / ~~`compile_directory()`~~ — all FEAT-002, none present at `dev@477544e`. Do not import or assume them.
- ~~`template_string=` as a `send()` keyword~~ — explicitly rejected (§1 Non-Goals, §9 Q1). Overload `template=` instead.
- ~~`TemplateSource` wrapper class~~ — considered and rejected (§9 Q1).
- ~~A per-provider `_prepare_` override~~ — verified none exists (`grep -rn "def _prepare_" notify/` → one hit, `base.py:116`). Do not add one.
- ~~`self.logger` on `TemplateParser`~~ — the module has **no logger** today; Module 1 must create one (`logging.getLogger("Notify.TemplateParser")`).
- ~~`notify/conf.py::TEMPLATE_DEBUG`~~ — not defined in `conf.py`; read ad hoc via `config.getboolean` at `notify/templates.py:37-39`.
- ~~`tests/test_jinja_string_templates.py`~~ / ~~`tests/test_templates.py`~~ — neither exists. Current suite: `tests/test_email_utf8.py`, `tests/test_outlook.py`, `tests/test_outlook1.py`, `tests/test_ses.py`, `tests/sdd_scripts/`.
- ~~Template support in OneSignal~~ — `Onesignal.send()` (`onesignal.py:93`) never calls `_prepare_`, and `grep -n "_template" notify/providers/onesignal/onesignal.py` returns nothing.
- ~~`.venv/bin/activate` as a usable activation script~~ — it carries a stale `VIRTUAL_ENV=/home/jesuslara/proyectos/navigator/notify/.venv`. Use `.venv/bin/python` directly, or recreate the venv with `uv venv`.

---

## 7. Implementation Notes & Constraints

### Patterns to Follow

- Google-style docstrings with strict type hints on every new/changed function
  and method (CLAUDE.md → Code Standards).
- `self.logger` from `navconfig.logging` — never `print`. `notify/templates.py`
  has no logger today; add one in Module 1.
- Async-first: `from_string()` is a *compile* step and stays synchronous, exactly
  like `get_template()`. It performs no I/O, so it is safe inside `_prepare_`.
- Keep `notify/templates.py` import-safe: no filesystem writes, no exceptions at
  import time.
- Package management via `uv`; the venv interpreter is `.venv/bin/python`.

### Known Risks / Gotchas

- **R1 — Heuristic false negative (the accepted trade-off).** A template body
  that is pure literal text with no Jinja markup and no newline
  (`template="Hello world"`) is indistinguishable from a filename and will be
  resolved on disk, raising `FileNotFoundError`. This is the known cost of
  overloading `template=` instead of adding a second keyword (§9 Q1).
  *Mitigation*: `template_is_source=True`; documented prominently in Module 5.
  Note that such a template has no variables, so the realistic blast radius is
  small — but the failure mode must be documented, not hidden.
- **R2 — Heuristic false positive would be a breaking change.** If the rules
  ever widened to classify a real filename as source, every existing caller
  would silently start rendering its own filename as a message body — a silent
  data-corruption bug, not a crash. *Mitigation*: the rules are restricted to
  Jinja delimiters and line breaks, and
  `test_is_template_source_rejects_plain_filenames` is a parametrised guard.
  **Do not add heuristics beyond the two in §2** (no `<`/`>` HTML sniffing, no
  length thresholds) without a spec revision.
- **R3 — Collision with FEAT-002.** `sdd/specs/templateparser-refactor.spec.md`
  is `approved` and already has task IDs reserved (`0b23c8b`); it rewrites
  `notify/templates.py`'s `__init__`, loader chain and error handling. Both
  features edit that file, and this spec was deliberately scoped independent of
  it (§9 Q2). *Mitigation*: whichever merges second rebases. `from_string()` is
  additive and depends only on `self.env` existing, so it survives FEAT-002's
  rewrite; the merge conflict will be textual (in `__init__`), not semantic.
  Do **not** rewrite `from_string()` in terms of FEAT-002's `render_string()` —
  see §6 "Does NOT Exist".
- **R4 — Unbounded cache growth.** Per-tenant or per-request template bodies
  would grow a naive cache without limit. *Mitigation*: bounded LRU
  (`OrderedDict` + `move_to_end` + `popitem(last=False)`), default 128, tunable
  via `string_cache_size`, plus `cache=False` for genuinely one-shot bodies.
- **R5 — The cache lives on a process-wide singleton.** `TemplateEnv`
  (`notify/notify.py:85-87`) is shared by every provider instance in the
  process, so all of them share one cache. Keying on `sha256(source)` means no
  cross-tenant content leakage, but a workload of unique bodies will thrash the
  LRU. Documented, not solved here.
- **R6 — Thread-safety.** With `blocking=True` the base `send()` runs `_send_`
  on `ThreadMessage` threads, and `blocking='executor'` uses a
  `ThreadPoolExecutor`. `_prepare_` itself is always awaited on the event loop,
  but `from_string()` is public and reachable from those threads.
  *Mitigation*: guard every cache read-modify-write with `threading.Lock`.
- **R7 — OneSignal is not covered.** `Onesignal.send()` (`onesignal.py:93`)
  overrides `send()` without calling `_prepare_`, so it supports neither file
  nor string templates. Pre-existing; explicitly out of scope. Do not "fix it
  while you're there" — that is a separate spec.
- **R8 — `template` leaks into the template variables.** `send()` forwards the
  *same* `kwargs` dict to both `_prepare_` and `_send_`, and `_render_` folds
  `**kwargs` into `self._templateargs` (`base.py:177-183`). So `{{ template }}`
  and `{{ template_is_source }}` resolve inside the rendered template. This is
  pre-existing behaviour for `template=`; with source strings the variable now
  holds the entire body. Harmless (nothing references it) but surprising —
  document it, and do **not** try to fix it by popping keys, which would change
  `_send_`'s kwargs for every provider.
- **R9 — Constructor/kwarg name collision.** `ProviderBase.__init__` sets every
  unconsumed kwarg as an instance attribute (`base.py:76-80`), so
  `Notify("smtp", template_is_source=True)` creates a `self.template_is_source`
  attribute. `_prepare_` deliberately reads only its **parameter**, never the
  attribute — a provider-level default is a separate feature (§9). Do not add
  an implicit `getattr(self, "template_is_source", None)` fallback.
- **R10 — SECURITY: string templates are an SSTI surface.** `autoescape` is
  `False` (`notify/templates.py:7-10` sets no `autoescape` key, so it is Jinja2's
  default `False`) and stays `False` (§1 Non-Goals). Compiling caller-supplied
  source therefore executes arbitrary Jinja2 — attribute traversal, `{% for %}`
  loops, registered globals and filters — and emits unescaped output. Template
  **source** must come from trusted operators (config, DB rows written by
  staff), never from end-user input; end-user data belongs in the **params**,
  which are just variables. This must be stated explicitly in the Module 5 docs,
  next to the feature's own usage example.
- **R11 — Pre-existing: sync render inside a running event loop.** With
  `enable_async=True`, `jinja2.Template.render()` runs `loop.run_until_complete`,
  which raises `RuntimeError` when a loop is already running. This affects
  `base.py:164` and `smtp.py:189` today, equally for file and string templates.
  Out of scope — do not fix, do not make worse.

### External Dependencies

| Package | Version | Reason |
|---|---|---|
| `jinja2` | `>=3.1.4` (already pinned, `pyproject.toml:41`) | `Environment.from_string`, `Template` and `TemplateSyntaxError` all ship in 3.1 — **no new dependency and no version bump** |

Everything else this feature needs (`hashlib`, `threading`, `collections`) is
stdlib. No `pyproject.toml` change is required.

---

## 8. Worktree Strategy

- **Default isolation unit**: `per-spec`.
- All five modules run **sequentially in one worktree**. Module 2 cannot be
  written before Module 1's `from_string()` exists, Module 4 exercises both, and
  Module 5 documents the final signatures.
- Modules 3 (`notify/models.py`) and 5 (`docs/`, `README.md`, `version.py`)
  share no file with any other module and are therefore marked
  `parallel: true` in the task index — they *could* run in separate worktrees.
  Given the feature is five small tasks, running them sequentially in the one
  per-spec worktree remains the recommended path; the flag records the
  file-level independence, not an instruction to fan out.
- **Module 3 is independently droppable.** It implements §9 Q5 (widening
  `Message.template`). If that decision is reversed, delete its task and its
  three tests; no other task references `notify/models.py`.
- Module 5 bumps `notify/version.py` to `1.6.0`. **FEAT-002 bumps the same
  file to the same value**, so expect a trivial both-added conflict there on
  whichever branch merges second.
- **Cross-feature dependencies**: none *declared* — this spec is deliberately
  independent of FEAT-002 (§9 Q2). But both features edit `notify/templates.py`,
  so the two worktrees will conflict textually on merge. Whichever lands second
  rebases onto `dev`; see §7 R3 for why the conflict is textual rather than
  semantic. FEAT-001 (NAV-8390 email UTF-8) is already merged and touches only
  `notify/providers/*` and `_mime_utils`.

```bash
git worktree add -b feat-003-jinja-string-notify \
  .claude/worktrees/feat-003-jinja-string-notify HEAD
```

---

## 9. Open Questions

> No brainstorm document preceded this spec. The questions below were asked and
> resolved directly with the author during `/sdd-spec`.

- [x] How should template-as-text be expressed in the `send()` API? —
  *Resolved by author*: **overload `template=`** with a heuristic that
  distinguishes a filename from Jinja source. A separate `template_string=`
  keyword and a `TemplateSource(...)` wrapper type were both presented and
  rejected. Reflected in §1 G3, §2 Overview + heuristic table, §3 Module 2,
  §5, and §7 R1/R2.
  *Recorded caveat*: the author was told a heuristic is inherently ambiguous;
  the accepted residual failure mode is documented as §7 R1, and the
  `template_is_source=` escape hatch (§1 G6) exists specifically to close it.
  If the author prefers the heuristic with **no** escape hatch, strike G6,
  the `template_is_source` parameter, and the four tests that cover it — the
  rest of the spec stands unchanged.
- [x] What is the relationship to FEAT-002 (`templateparser-refactor`)? —
  *Resolved by author*: **independent**. Build on `notify/templates.py` as it
  stands at 1.5.7; do not depend on, wait for, or absorb FEAT-002. Reflected
  in §1 Non-Goals, §6 "Does NOT Exist", §7 R3, and §8.
- [x] Should compiled string templates be cached? — *Resolved by author*:
  **yes, an LRU keyed by a hash of the source**. Reflected in §1 G5, §2
  Overview, §2 Data Models, §4, §5, and §7 R4/R5/R6.
- [x] Target version? — *Author's choice of 1.6.0*, matching FEAT-002: the
  change is additive and backward compatible. Reflected in the header and §5.

Remaining for implementation time:

- [ ] Confirm `DEFAULT_STRING_CACHE_SIZE = 128` is a sensible default, or make it
  configurable through navconfig (`TEMPLATE_STRING_CACHE_SIZE`) rather than only
  a constructor kwarg — *Owner: implementer*
- [ ] Decide whether a provider-level default (`Notify("smtp", template_is_source=True)`
  honoured by `_prepare_`) is worth a follow-up spec. Deliberately **not**
  implemented here; see §7 R9 — *Owner: Jesus Lara*
- [x] **(Q5)** Decide whether `notify/models.py::Message.template` should widen
  from `Path` to `Union[Path, str]` so the model can carry inline source too —
  *Owner: Jesus Lara*: **Yes**.
  *Routed into*: §1 G8 (new goal, replacing the former non-goal), §2
  Integration Points, §3 Module 3, §4 (three model tests), §5, §6 (models
  contract + the "no consumers" evidence table), §8.
  *Assumption recorded*: the question asked whether the model should widen
  "later"; it is being implemented **inside FEAT-003** rather than deferred to
  a follow-up spec, because it is a one-line type change with no consumers in
  the package. It is isolated in its own task so it can be dropped from this
  feature without touching any other task if that reading is wrong.

---

## Revision History

| Version | Date | Author | Change |
|---|---|---|---|
| 0.1 | 2026-08-06 | Jesus Lara | Initial draft — inline Jinja2 template source for `send()`, derived from a code audit of `ProviderBase._prepare_` and `TemplateParser` |
