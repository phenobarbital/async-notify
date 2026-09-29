---
type: feature
base_branch: dev
---

# Feature Specification: Actionable optional-dependency diagnostics and a slim core install

**Feature ID**: FEAT-005
**Date**: 2026-09-29
**Author**: Jesus Lara (jlara@trocglobal.com)
**Status**: approved
**Target version**: 1.7.0

> **Slug note.** The slug `lazy-import-providers` is retained because it owns
> FEAT-005 in `sdd/tasks/.id_ledger.json` and in the committed proposal;
> renaming it would fork the feature identity. The *title* is re-aimed: the
> original premise ("all providers are imported at startup") was disproved
> during research — see §1.
>
> **Proposal**: [`sdd/proposals/lazy-import-providers.proposal.md`](../proposals/lazy-import-providers.proposal.md)
> · **Research audit**: [`sdd/state/FEAT-005/`](../state/FEAT-005/)

---

## 1. Motivation & Business Requirements

### Problem Statement

The originating request was:

> async-notify carga al arranque todos los providers de comunicación, estén
> instaladas sus dependencias o no, hay que hacer un lazy-import para reducir
> el startup cost de notify

**That premise does not hold.** Providers are already lazy: `LoadProvider`
resolves them with `importlib.import_module` at call time and memoises them in
`PROVIDERS` (`notify/notify.py:70-86`), `notify/providers/__init__.py` is a bare
docstring, and no module under `notify/` imports a concrete provider. There is
no eager fan-out to remove.

Research did surface three real problems behind the reported symptoms:

1. **A missing optional SDK is indistinguishable from a typo.** With `aiogram`
   blocked, `Notify("telegram")` and `Notify("does_not_exist")` both raise
   `ProviderError: Cannot Load provider <x>: Error: No Provider <x> was Found:
   …`, both logged at CRITICAL, neither naming the extra to install. The only
   discriminator is buried in the chained `ModuleNotFoundError`.
2. **The core install carries dependencies nothing on the core path uses.**
   `pillow` is a core dependency that **no module in `notify/` imports at all**;
   `emoji` is used only by telegram, `aiobotocore` only by ses, `cloudpickle`
   only by `notify/server`.
3. **`import notify` costs ~196 ms**, dominated by navconfig (~124 ms), with
   datamodel and jinja2 pulled in by `notify/providers/base.py` for an
   annotation and a pure string predicate.

Research also uncovered two latent defects in the exact function this feature
rewrites (both confirmed by the independent design review, §9):

4. **`Notify("smtp")` is broken today.** `LoadProvider` resolves the class with
   `getattr(module, provider.capitalize())` → `Smtp`, but the package exports
   `SMTP`. Reproduced: `ProviderError: module 'notify.providers.smtp' has no
   attribute 'Smtp'`.
5. **`LoadProvider`'s `except ImportError` fallback is dead code.** It re-imports
   the classpath that just failed and, on success, would return the *module*
   instead of the class.

### Goals

- **G1 — Actionable missing-dependency diagnostics.** A missing optional SDK
  raises a distinct, catchable exception naming the provider, the missing
  distribution, and the exact `pip install async-notify[<extra>]` command, and
  is distinguishable from an unknown provider name both by type and by message.
- **G2 — Correct provider resolution.** `Notify("<alias>")` resolves the
  provider class through the package's export contract, so every documented
  alias works — including `smtp`, which does not today.
- **G3 — Slim core install.** `pip install async-notify` installs only what the
  provider-agnostic core path needs: no provider-only or server-only SDK.
- **G4 — A per-provider extra for every provider that needs a third-party SDK**,
  so the G1 message can always name a precise extra.
- **G5 — Discoverable install story.** README documents the extras matrix;
  `CHANGES.rst` documents the migration.
- **G6 (secondary) — Bounded import-cost reduction.** Defer datamodel and jinja2
  out of the startup path, taking `import notify` from ~196 ms to **~165 ms**
  (see §2 "Revised import-cost budget" — this supersedes the proposal's ~123 ms
  figure, which double-counted a shared dependency subtree).

### Non-Goals (explicitly out of scope)

- **Making `notify/providers/*` lazy — they already are.** No work exists in
  that layer.
- **Deferring navconfig / making `notify/conf.py` lazy.** Explicitly scoped out
  by the user during proposal Q&A (U2). It is the single largest remaining cost
  (~124 ms of the ~165 ms post-change total) and would need its own cycle:
  `conf.py` exports ~42 eagerly-evaluated module constants consumed by the
  server and by providers.
- A provider registry, plugin discovery, or entry-point-based loading.
- Deriving `PROVIDER_EXTRAS` from package metadata at runtime — the user chose a
  hand-maintained mapping.
- Changing the `ProviderBase` / `_send_` contract, or any provider's runtime
  behaviour.
- Reducing the install weight of the `all` extra.
- Declaring every currently-undeclared transitive dependency. Only those a
  provider imports *directly* and that lose their declaring parent as a result
  of this change are in scope (see §7, "Undeclared direct imports").

---

## 2. Architectural Design

### Overview

Four independent workstreams, only the last of which touches import timing.

**A. Diagnostics and resolution (`notify/notify.py`, `notify/exceptions.pyx`).**
`LoadProvider` is rewritten around one discriminator: the `name` attribute of
the `ModuleNotFoundError` that `importlib.import_module` raises.

- `exc.name == "notify.providers.<alias>"` → the provider itself does not exist
  → `ProviderError` ("unknown provider"), listing the known aliases.
- `exc.name` is anything else → the provider module exists but one of *its*
  imports failed → `ProviderDependencyError`, naming the missing top-level
  module and the extra that ships it.

This is precise: it cannot misclassify a genuine bug inside a provider module as
a missing dependency, because such a failure is not a `ModuleNotFoundError` at
all (or carries a `notify.*` name). The dead `__import__` fallback is deleted.
Class resolution moves from `provider.capitalize()` to the package's `__all__`.

`ProviderDependencyError` subclasses `ProviderError`, so existing
`except ProviderError` handlers keep working. `Notify.__new__` and
`Notify.provider()` currently catch `Exception` and re-raise a flat
`ProviderError`, which would erase the subclass — both must re-raise a
`ProviderError` (and therefore `ProviderDependencyError`) unchanged.

**B. Dependency manifest (`pyproject.toml`, `uv.lock`).** Four packages leave
core; five new extras are added; `aiohttp` is *promoted* into core because three
providers import it directly and it is currently present only as a transitive
dependency of `aiobotocore` — which is leaving core. `uv.lock` must be
regenerated or reproducible installs silently keep the old core set.

**C. Bounded import deferrals (`notify/providers/base.py`, `notify/utils/templates.py`).**
`notify/providers/base.py` has 21 ms of self time but 214 ms cumulative. Two of
its three heavy edges are nearly free to cut:
- `Actor` is used at lines 119, 169, 189, 210, 228 and 265 — **every use is an
  annotation** → `TYPE_CHECKING` + `from __future__ import annotations`.
- `is_template_source` is a pure string predicate with no jinja2 dependency of
  its own; it merely lives in a module that imports jinja2 → move the function
  and `JINJA_MARKERS` to a jinja2-free module, re-exported from
  `notify.templates` for compatibility.

`notify/notify.py`'s module-level `from .conf import TEMPLATE_DIR` and
`from .templates import TemplateParser` serve only the deliberately-lazy
`__getattr__`; they move inside it.

**D. Documentation (`README.md`, `CHANGES.rst`).**

### Revised import-cost budget

The proposal's C13 claimed ~192 → ~123 ms. **Re-measurement during this spec
shows that figure was too optimistic**: it subtracted the cost of datamodel and
jinja2 measured *cold*, but those trees overlap heavily with navconfig's, and
navconfig stays (`base.py:12` needs `DEBUG`, `notify.py:3` needs the logger).
The marginal saving must therefore be measured **with navconfig already loaded**:

| Measurement (Python 3.11, warm FS cache, 3-5 runs) | Result |
|---|---|
| `import notify`, cold | **196-203 ms** |
| `import navconfig`, cold | 123-127 ms |
| `import notify` with navconfig preloaded | 70.2 ms |
| `import notify` with navconfig + datamodel preloaded | 49.0 ms |
| `import notify` with navconfig + jinja2 preloaded | 58.4 ms |
| `import notify` with navconfig + datamodel + jinja2 preloaded | 36.5 ms |

Marginal cost of datamodel **given navconfig** ≈ 21 ms; of jinja2 ≈ 12 ms;
of both ≈ **34 ms**. Projected post-change cold import ≈ 124 + 36.5 ≈
**~161-170 ms**, i.e. a **~17-20% reduction**, not the ~36% the proposal
projected. §5 sets the acceptance threshold accordingly, and requires the
number to be measured in the worktree rather than trusted from this table.

### Component Diagram

```
Notify("telegram")                      pip install async-notify
   │                                         │
   ▼                                         ▼
LoadProvider(alias)                    [project] dependencies   ← slimmed (M2)
   │                                    aiosmtplib, python-datamodel,
   ├─ importlib.import_module           navconfig, jinja2, aiohttp
   │     │
   │     ├─ ok ──► resolve class via __all__  ──► provider class
   │     │
   │     └─ ModuleNotFoundError
   │            │
   │            ├─ name startswith "notify.providers."
   │            │      └──► ProviderError  (unknown provider; lists aliases)
   │            │
   │            └─ else  ──► PROVIDER_EXTRAS[alias]
   │                            └──► ProviderDependencyError
   │                                 "…install async-notify[telegram]"
   │
   └─ memoised in PROVIDERS

notify/providers/base.py   ──TYPE_CHECKING──►  notify.models (datamodel)   ← deferred (M3)
          │
          └── is_template_source ──► notify/utils/templates.py  (no jinja2)  ← new (M3)
                                            ▲
                          notify/templates.py re-exports (compat)
```

### Integration Points

| Existing Component | Integration Type | Notes |
|---|---|---|
| `LoadProvider` (`notify/notify.py:70-86`) | rewritten | same signature, same memoisation contract |
| `Notify.__new__` / `Notify.provider` (`notify/notify.py:31-67`) | modified | must re-raise `ProviderError` subclasses unchanged |
| `ProviderError` (`notify/exceptions.pyx:30`) | extended | new subclass `ProviderDependencyError` |
| `ProviderBase` (`notify/providers/base.py:31`) | modified imports only | no behavioural change |
| `notify.templates.is_template_source` (`notify/templates.py:95`) | moved + re-exported | import path `notify.templates` must keep working |
| `notify/server/wrapper.py:105,114` | unchanged | already routes through the lazy factory |
| `notify/__main__.py:4` | affected | imports `notify.server`; needs the new `server` extra |

### Data Models

No new Pydantic/datamodel structures. One module-level constant:

```python
# notify/notify.py
PROVIDER_EXTRAS: dict[str, str] = {...}   # factory alias -> pyproject extra name
```

**The map is keyed by factory alias (the package directory name), never by the
provider class's `provider` attribute.** Those disagree for four providers and
would silently mis-key the mapping:

| package / factory alias | `cls.provider` value |
|---|---|
| `ses` | `amazon_ses` |
| `twilio` | `sms` |
| `aws` | `aws_email` |
| `smtp` | *(attribute absent)* |

### New Public Interfaces

```python
# notify/exceptions.pyx
cdef class ProviderDependencyError(ProviderError):
    """A provider's optional third-party SDK is not installed."""
```

---

## 3. Module Breakdown

#### Delegation-eligible modules

| Module | Eligible? | Decided patterns / exact contracts | Why not (if no) |
|---|---|---|---|
| M1: Provider resolution & dependency diagnostics | yes | Exception name, base class, discrimination rule (`ModuleNotFoundError.name`), class resolution via `__all__`, exact `PROVIDER_EXTRAS` contents, message template — all fixed in §6 | — |
| M2: Dependency manifest | yes | Exact core set, exact extras and their contents, invariants to preserve — all fixed below | — |
| M3: Bounded import deferrals | yes | Target file `notify/utils/templates.py`, symbols to move, re-export contract, `TYPE_CHECKING` shape | — |
| M4: Documentation | yes | Extras matrix is fully determined by M2 | — |
| M5: Tests | yes | Each assertion named in §4 | — |

### Module 1: Provider resolution & dependency diagnostics
- **Path**: `notify/notify.py`, `notify/exceptions.pyx`, `notify/exceptions.pxd`
- **Responsibility**: resolve a provider alias to its class, and turn every
  failure into a precise, actionable, correctly-typed error.
- **Depends on**: M2 for the extra names it cites (develop against the agreed
  table in §6; the two can land in either order).
- **Interface Skeleton** *(signatures + docstrings only)*:
  ```python
  # notify/exceptions.pyx  (adds to notify/exceptions.pyx:30 ProviderError)
  cdef class ProviderDependencyError(ProviderError):
      """Raised when a provider's optional third-party SDK is missing.

      Distinguishes "this provider needs a package you have not installed"
      from "this provider does not exist", which ``ProviderError`` alone
      cannot express.
      """

  # notify/exceptions.pxd  (mirror of the .pyx declaration — keep in sync)
  cdef class ProviderDependencyError(ProviderError):
      """Raised when a provider's optional third-party SDK is missing."""

  # notify/notify.py  (modifies notify/notify.py:70-86)
  PROVIDER_EXTRAS: dict[str, str] = {...}
  """Factory alias -> ``pyproject.toml`` extra that ships its SDK.

  Keyed by the package directory name under ``notify/providers/`` — i.e.
  the string callers pass to ``Notify()`` — never by ``cls.provider``,
  which disagrees for ses/twilio/aws (verified: notify/providers/ses/ses.py,
  notify/providers/twilio/twilio.py, notify/providers/aws/aws.py).
  Providers whose only dependencies are core carry no entry.
  """

  def LoadProvider(provider: str) -> type:  # modifies notify/notify.py:70
      """Dynamically load a Notify provider class by factory alias.

      Args:
          provider: Factory alias, i.e. the package directory name under
              ``notify/providers/`` (e.g. ``"telegram"``, ``"smtp"``).

      Returns:
          The provider class exported by ``notify.providers.<provider>``,
          resolved through that package's ``__all__``.

      Raises:
          ProviderDependencyError: The provider module exists but a
              third-party module it imports is missing. The message names
              the missing module and, when known, the extra that ships it.
          ProviderError: No such provider, or the package exports no
              resolvable provider class. The message lists known aliases.
      """

  def _known_providers() -> tuple[str, ...]:  # new, module-private
      """Return the sorted factory aliases discoverable on disk.

      Used only to build the "unknown provider" message; never imports a
      provider module.
      """
  ```
- **Behavioural contract (fixed here, not renegotiable in tasks)**:
  - Discrimination is on `ModuleNotFoundError.name`. A missing name that
    equals or starts with `notify.providers.` ⇒ unknown provider. Any other
    missing name ⇒ dependency error.
  - An `ImportError` that is *not* a `ModuleNotFoundError`, and any other
    exception raised while importing the provider module, propagates with its
    original type and `__cause__` intact. It must never be reported as a
    missing dependency.
  - Class resolution: take the single name in the package's `__all__`; if
    `__all__` is absent or does not resolve, raise `ProviderError` naming the
    package. Do **not** fall back to `.capitalize()`.
  - `PROVIDERS` memoisation semantics are unchanged; failures are not cached.
  - `Notify.__new__` / `Notify.provider` re-raise `ProviderError` and its
    subclasses unchanged, and log the failure at `error`, not `critical`
    (the exception already reaches the caller; CRITICAL double-reports a
    recoverable, user-caused condition).

### Module 2: Dependency manifest
- **Path**: `pyproject.toml`, `uv.lock`
- **Responsibility**: a core install that carries only core needs, and one
  extra per provider that needs a third-party SDK.
- **Depends on**: nothing.
- **Exact target state**:
  ```toml
  # pyproject.toml:36-45  (core: -pillow -emoji -aiobotocore -cloudpickle +aiohttp)
  dependencies = [
    "aiosmtplib>=5.0",
    "python-datamodel>=0.3.12",
    "navconfig[default]>=2.2.0",
    "jinja2>=3.1.4",
    "aiohttp>=3.10",
  ]

  # pyproject.toml:47+  new extras
  ses    = ["aiobotocore>=2.15.2"]
  slack  = ["slack_bolt>=1.18.0"]
  twilio = ["twilio>=8.2.2"]
  xmpp   = ["slixmpp>=1.10.0"]
  server = ["cloudpickle>=3.1.0", "qworker>=1.12.7", "redis>=5.0"]

  # telegram gains the emoji dependency it is the sole consumer of
  telegram = ["aiogram>=3.14.0", "moviepy>=2.2.1", "emoji>=1.7.0"]

  # azure gains redis, imported by the O365 token store
  azure = [..., "redis>=5.0"]
  ```
- **Invariants that MUST survive** (asserted by an existing test —
  `tests/test_office365_configuration.py:42-58`): the `azure` and `all` extras
  both continue to exist and to contain `cryptography>=42.0`, and neither
  reintroduces `pyo365`, `o365`, or `Office365-REST-Python-Client`.
- **`all` must remain a true superset**: it gains `emoji` and `cloudpickle`
  (moved out of core) and keeps everything else. `pillow` is dropped outright,
  from core and everywhere else — nothing in `notify/` imports PIL.
- **`uv.lock` must be regenerated** (`uv lock`) in the same commit. It currently
  records `aiobotocore`, `cloudpickle`, `emoji` and `pillow` as core
  dependencies of `async-notify` (`uv.lock:470-477`); editing only
  `pyproject.toml` leaves reproducible installs on the old set.

### Module 3: Bounded import deferrals
- **Path**: `notify/utils/templates.py` (new), `notify/templates.py`,
  `notify/providers/base.py`, `notify/notify.py`
- **Responsibility**: remove datamodel and jinja2 from the `import notify` path
  without changing any public import path.
- **Depends on**: nothing.
- **Interface Skeleton**:
  ```python
  # notify/utils/templates.py  (new — MUST NOT import jinja2, datamodel or navconfig)
  JINJA_MARKERS: tuple[str, ...] = ("{{", "{%", "{#")
  """Jinja2 delimiters that can never appear in a template *filename*."""

  def is_template_source(value: str) -> bool:
      """Decide whether *value* is Jinja2 source text rather than a filename.

      Moved verbatim from notify/templates.py:95-114; behaviour unchanged.
      """

  # notify/templates.py  (modifies notify/templates.py:89,95)
  from notify.utils.templates import JINJA_MARKERS, is_template_source
  # Re-exported for backward compatibility: notify/providers/base.py:19 and
  # tests/test_jinja_string_templates.py:28-30 import both from here.
  # The re-export MUST be silent — pyproject.toml:159-162 sets
  # filterwarnings = ["error", ...], so a DeprecationWarning fails CI.

  # notify/providers/base.py  (modifies notify/providers/base.py:12-19)
  from __future__ import annotations
  from typing import TYPE_CHECKING
  from notify.utils.templates import is_template_source   # was: notify.templates
  if TYPE_CHECKING:
      from notify.models import Actor   # annotations only: lines 119,169,189,210,228,265

  # notify/notify.py  (modifies notify/notify.py:5,8 and :89-116)
  def __getattr__(name: str):
      """PEP 562 hook — unchanged contract.

      ``from .conf import TEMPLATE_DIR`` and ``from .templates import
      TemplateParser`` move inside this function: it is their only consumer.
      """
  ```
- **Constraint**: `notify/utils/templates.py` is reached through
  `notify/utils/__init__.py`, which imports `notify.utils.functions`. That
  module is pure-stdlib today and must stay that way, or the deferral is undone.

### Module 4: Documentation
- **Path**: `README.md`, `CHANGES.rst`
- **Responsibility**: make the extras discoverable, and the install change
  survivable.
- **Depends on**: M2 (the matrix is its output).
- **Content contract**:
  - README gains an "Installation" section with a provider → extra table
    covering all 17 providers, including those that need no extra, plus
    `pip install async-notify[all]` and `pip install async-notify[server]`.
  - `CHANGES.rst` gains a 1.7.0 entry listing each package that left core, the
    extra that now carries it, and the one-line remediation
    (`pip install async-notify[<extra>]`).
  - README must state that `notify` the console script requires the `server`
    extra (`notify/__main__.py:4` imports `notify.server`).

### Module 5: Tests
- **Path**: `tests/test_provider_dependencies.py` (new),
  `tests/test_startup_imports.py` (new), `tests/test_dependency_manifest.py` (new)
- **Responsibility**: lock every claim above.
- **Depends on**: M1, M2, M3.

---

## 4. Test Specification

### Unit Tests

| Test | Module | Description |
|---|---|---|
| `test_missing_sdk_raises_dependency_error` | M1 | With `aiogram` blocked via a `sys.meta_path` finder, `Notify("telegram")` raises `ProviderDependencyError`; the message contains `aiogram` and `async-notify[telegram]` |
| `test_unknown_provider_raises_provider_error` | M1 | `Notify("does_not_exist")` raises `ProviderError` but **not** `ProviderDependencyError` |
| `test_dependency_error_is_a_provider_error` | M1 | `issubclass(ProviderDependencyError, ProviderError)` — existing handlers keep working |
| `test_notify_factory_preserves_error_subclass` | M1 | `Notify.__new__` does not flatten `ProviderDependencyError` into `ProviderError` |
| `test_smtp_alias_resolves` | M1/G2 | `Notify("smtp")` returns an `SMTP` instance (fails on `dev` today) |
| `test_all_aliases_resolve_to_a_class` | M1 | Every package under `notify/providers/` resolves to a class via `__all__`, without instantiating it |
| `test_internal_import_error_is_not_masked` | M1 | A provider module raising a non-`ModuleNotFoundError` `ImportError` propagates unchanged, not as a dependency error |
| `test_provider_extras_names_exist_in_pyproject` | M2 | Every value in `PROVIDER_EXTRAS` is a key of `[project.optional-dependencies]` |
| `test_core_dependencies_are_minimal` | M2 | Core contains none of `pillow`, `emoji`, `aiobotocore`, `cloudpickle` |
| `test_all_extra_is_a_superset` | M2 | Every distribution in any non-`dev` extra also appears in `all` |
| `test_azure_invariants_preserved` | M2 | Re-assert `tests/test_office365_configuration.py:42-58` still passes unchanged |
| `test_is_template_source_reexported` | M3 | `from notify.templates import is_template_source, JINJA_MARKERS` still works and `JINJA_MARKERS == ("{{", "{%", "{#")` |
| `test_utils_templates_has_no_heavy_imports` | M3 | Importing `notify.utils.templates` in a clean subprocess leaves `jinja2`, `datamodel` and `navconfig` out of `sys.modules` |
| `test_readme_matrix_matches_manifest` | M4 | Every extra in `pyproject.toml` appears in the README table and vice versa |

### Integration Tests

| Test | Description |
|---|---|
| `test_import_notify_defers_heavy_modules` | In a **clean subprocess** (`subprocess.run([sys.executable, "-c", ...])`), `import notify` leaves `jinja2` and `datamodel` out of `sys.modules` |
| `test_deferred_modules_load_on_first_use` | In the same subprocess, after `notify.TemplateEnv` / a `_prepare_(template=…)` call, `jinja2` **is** in `sys.modules` — proving deferral, not deletion |
| `test_import_notify_within_budget` | Cold `import notify` measured in a subprocess stays under the §5 threshold |

> **A subprocess is mandatory for the three tests above.** In-process
> `sys.modules` manipulation cannot prove cold-start absence: the existing
> suite (`tests/test_templates_integration.py`, `tests/test_jinja_string_templates.py`)
> already imports `TemplateParser` and `TemplateEnv` at collection time, so
> `jinja2` is resident long before these assertions would run.

### Test Data / Fixtures

```python
# Blocking a third-party module for the diagnostic tests — the technique the
# research probe used, reproduced against the merged tree.
@pytest.fixture
def blocked_module(monkeypatch):
    """Make a top-level module unimportable for the duration of a test."""
    import importlib.abc, sys

    class _Blocker(importlib.abc.MetaPathFinder):
        def __init__(self, name): self.name = name
        def find_spec(self, fullname, path, target=None):
            if fullname == self.name or fullname.startswith(self.name + "."):
                raise ImportError(f"No module named {fullname!r} (blocked)")
            return None
    ...
    # Must also evict notify.providers.<alias> and the PROVIDERS entry, or
    # memoisation from an earlier test hides the failure.
```

---

## 5. Acceptance Criteria

> This feature is complete when ALL of the following are true:

- [ ] **G1** With its SDK blocked, `Notify("telegram")` raises
      `ProviderDependencyError` whose message names both `aiogram` and
      `pip install async-notify[telegram]`.
- [ ] **G1** `Notify("does_not_exist")` raises `ProviderError` and **not**
      `ProviderDependencyError`, and the message lists known aliases.
- [ ] **G1** A non-`ModuleNotFoundError` failure inside a provider module
      propagates with its original type and `__cause__`.
- [ ] **G1** Neither path logs at CRITICAL.
- [ ] **G2** `Notify("smtp")` returns an `SMTP` instance. *(Fails on `dev` today —
      this is a fix, not a regression guard.)*
- [ ] **G2** Every package under `notify/providers/` resolves to a class through
      its `__all__`.
- [ ] **G3** `[project] dependencies` contains none of `pillow`, `emoji`,
      `aiobotocore`, `cloudpickle`.
- [ ] **G3** `uv.lock` is regenerated and its `async-notify` core dependency
      list matches `pyproject.toml`.
- [ ] **G4** Every provider that imports a third-party SDK has an extra that
      ships it, and every value in `PROVIDER_EXTRAS` names a real extra.
- [ ] **G4** The `all` extra remains a superset of every other non-`dev` extra;
      `azure` and `all` still contain `cryptography>=42.0` and still exclude
      `pyo365` / `o365` / `Office365-REST-Python-Client`
      (`tests/test_office365_configuration.py` passes **unmodified**).
- [ ] **G5** README carries a provider → extra matrix covering all 17 providers
      and notes the `server` extra requirement for the `notify` console script;
      `CHANGES.rst` has a 1.7.0 migration entry.
- [ ] **G6** In a clean subprocess, `import notify` leaves `jinja2` and
      `datamodel` out of `sys.modules`, and both appear after first template use.
- [ ] **G6** Cold `import notify`, measured in the worktree **after**
      `python setup.py build_ext --inplace`, is **≤ 175 ms** against a
      re-measured pre-change baseline on the same machine, and the measured
      before/after pair is recorded in the task's completion note.
      *(Projection is ~161-170 ms; the threshold carries headroom because the
      projection is arithmetic over preload attribution, not a patched build.
      If the measurement lands above 175 ms, report it rather than tuning the
      threshold.)*
- [ ] `from notify.templates import is_template_source, JINJA_MARKERS` still
      works, silently (no warning — `filterwarnings = ["error", ...]`).
- [ ] No breaking change to the public Python API: `notify.__all__` is
      unchanged and `except ProviderError` still catches every load failure.
- [ ] Full suite passes: `PYTHONPATH=. pytest tests/ -v` (after
      `python setup.py build_ext --inplace`).
- [ ] `black --line-length 120`, `flake8` and `pylint` clean on changed files.

---

## 6. Codebase Contract

> **CRITICAL — Anti-Hallucination Anchor.**
> Every entry below was re-verified on 2026-09-29 against the merged tree
> (`dev` @ `3d0f0f9`, i.e. after FEAT-004 `mail-messages-graph` landed). The
> FEAT-005 proposal was researched *before* that merge; line numbers that moved
> are corrected here and this section wins.

### Verified Imports

```python
from notify import Notify                                   # verified: notify/__init__.py:7
from notify.providers.base import ProviderType              # verified: notify/__init__.py:6
from notify.exceptions import NotifyException, ProviderError  # verified: notify/notify.py:6
from notify.templates import is_template_source, JINJA_MARKERS  # verified: notify/templates.py:89,95
from notify.models import Actor                             # verified: notify/providers/base.py:18
from notify.utils.uv import install_uvloop                  # verified: notify/utils/uv.py:6
```

### Existing Class Signatures

```python
# notify/notify.py
PROVIDERS = {}                                              # line 10
_TEMPLATE_ENV: TemplateParser | None = None                 # line 15

class Notify:
    def __new__(cls, provider: str, *args, **kwargs):       # line 31
        # wraps EVERY exception into ProviderError(message=...)  # lines 42-48
    @classmethod
    def provider(cls, provider: str, *args, **kwargs):      # line 51
        # same wrapping                                      # lines 61-67

def LoadProvider(provider: str):                            # line 70
    classpath = f"notify.providers.{provider}"              # line 76
    module = importlib.import_module(classpath, package="providers")  # line 77
    return getattr(module, provider.capitalize())           # line 78  <- the smtp bug
    # except ImportError: re-imports the same classpath, returns the MODULE  # lines 79-82 (dead)
    # raise NotifyException(f"Error: No Provider {provider} was Found: {exc}")  # lines 84-86

def __getattr__(name: str):                                 # line 89 — PEP 562 precedent
def __dir__() -> list[str]:                                 # line 119

# notify/exceptions.pyx   (Cython — rebuild with: python setup.py build_ext --inplace)
cdef class NotifyException(Exception):                      # line 5
    def __init__(self, str message, int code = 0, str payload = None, **kwargs)  # line 10
cdef class NotSupported(NotifyException):                   # line 26
cdef class ProviderError(NotifyException):                  # line 30
cdef class MessageError(NotifyException):                   # line 34
cdef class UninitializedError(ProviderError):               # line 38
cdef class NotifyTimeout(ProviderError):                    # line 42
cdef class NotifyAuthError(ProviderError):                  # line 45

# notify/providers/base.py
from navconfig import DEBUG                                 # line 12  (runtime use at line 64 — NOT deferrable)
from notify.models import Actor                             # line 18  (annotations only — deferrable)
from notify.templates import is_template_source             # line 19  (deferrable)
class ProviderBase(ABC):                                    # line 31
    async def _prepare_(self, recipient: Actor = None, ...) # line 117
        use_source = is_template_source(template)           # line 155  (sole call site)
# Actor referenced at lines 119, 169, 189, 210, 228, 265 — every one an annotation

# notify/templates.py
JINJA_MARKERS: tuple[str, ...] = ("{{", "{%", "{#")         # line 89
def is_template_source(value: str) -> bool:                 # line 95  (pure string predicate, 95-114)
from jinja2 import (...)                                    # line 11  (why this module is heavy)

# notify/server/wrapper.py
notify: coro = Notify(self._provider, **self.kwargs)        # lines 105, 114  (was 71,83 pre-FEAT-004)
```

### Provider → SDK → extra table (verified by AST scan of every provider package)

| Factory alias (dir) | Exported class (`__all__`) | `cls.provider` | Direct third-party imports | Extra |
|---|---|---|---|---|
| `aws` | `Aws` | `aws_email` | — | *(none needed)* |
| `dialpad` | `Dialpad` | `dialpad` | `aiohttp` | *(core)* |
| `dummy` | `Dummy` | `dummy` | — | *(none needed)* |
| `email` | `Email` | `email` | — | *(none needed)* |
| `gmail` | `Gmail` | `gmail` | `gmail` | `google` |
| `office365` | `Office365` | `office365` | `msal`, `msgraph`, `msgraph_core`, `azure`, `cryptography`, `aiofiles`, `redis` | `azure` |
| `onesignal` | `Onesignal` | `onesignal` | `onesignal_sdk`, `requests` | `push` |
| `outlook` | `Outlook` | `outlook` | — *(alias of office365)* | `azure` |
| `sendgrid` | `Sendgrid` | `sendgrid` | — *(SMTP-based)* | *(none needed)* |
| `ses` | `Ses` | `amazon_ses` | `aiobotocore` | **`ses` (new)** |
| `slack` | `Slack` | `slack` | `slack_bolt`, `slack_sdk` | **`slack` (new)** |
| `smtp` | **`SMTP`** | *(absent)* | — | *(none needed)* |
| `teams` | `Teams` | `teams` | `aiohttp`, `azure`, `msal`, `msgraph`, `kiota_abstractions` | `azure` |
| `telegram` | `Telegram` | `telegram` | `aiogram`, `emoji`, `moviepy` | `telegram` |
| `twilio` | `Twilio` | `sms` | `twilio` | **`twilio` (new)** |
| `xmpp` | `Xmpp` | `xmpp` | `slixmpp` | **`xmpp` (new)** |
| `zoom` | `Zoom` | `zoom` | `aiohttp` | *(core)* |

`notify/server/` imports `cloudpickle`, `qw` (qworker) and `redis`
(`notify/server/client.py:5-6`, `notify/server/server.py:10-12`) → **`server` (new)**.

### Integration Points

| New Component | Connects To | Via | Verified At |
|---|---|---|---|
| `ProviderDependencyError` | `ProviderError` | subclass | `notify/exceptions.pyx:30` |
| `PROVIDER_EXTRAS` | `LoadProvider` | dict lookup on the alias argument | `notify/notify.py:70,76` |
| `LoadProvider` | `ModuleNotFoundError.name` | attribute read on the caught exception | stdlib |
| `notify/utils/templates.py` | `ProviderBase._prepare_` | direct import | `notify/providers/base.py:19,155` |
| `notify/utils/templates.py` | `notify.templates` | re-export for compatibility | `tests/test_jinja_string_templates.py:28-30` |

### Does NOT Exist (Anti-Hallucination)

- ~~`notify.providers.registry`~~ / ~~`notify.providers.PROVIDERS`~~ — the
  registry is `PROVIDERS` in `notify/notify.py:10`, nowhere else.
- ~~`notify.providers.__init__` exports~~ — it is a bare docstring; no provider
  is importable from the package root.
- ~~`ProviderBase.provider_extra`~~ / ~~`ProviderBase.required_packages`~~ —
  no such attribute. Do not add one; the map is keyed by alias, not by class.
- ~~`notify.exceptions.ProviderDependencyError`~~ — **does not exist yet**; M1
  creates it. Nothing may import it before M1 lands.
- ~~`notify.utils.templates`~~ — **does not exist yet**; M3 creates it.
- ~~`Smtp`~~ — the smtp package exports `SMTP`
  (`notify/providers/smtp/__init__.py`). `provider.capitalize()` produces
  `Smtp`, which is why `Notify("smtp")` fails today.
- ~~`pillow` / `PIL` usage~~ — zero imports anywhere under `notify/`.
- ~~`NotifyAuthError` in `notify/exceptions.pxd`~~ — present in the `.pyx`
  (line 45) but **missing from the `.pxd`**. Pre-existing drift; see §7.
- ~~`typing.get_type_hints` callers~~ — zero occurrences in the repository
  (verified by repo-wide grep excluding `.venv`).
- ~~`aiohttp` / `requests` / `aiofiles` / `redis` in `pyproject.toml`~~ — none
  of these are declared today despite being imported directly; see §7.

---

## 7. Implementation Notes & Constraints

### Patterns to Follow

- **PEP 562 module `__getattr__` with a private memoisation slot** —
  `notify/notify.py:89-116` (`_TEMPLATE_ENV`). M3 extends this exact idiom.
- **Deferred import + a message naming the extra** —
  `notify/providers/telegram/Telegram.py:341-348` already does this for
  `moviepy`. M1 generalises that message shape; do not invent a new one.
- **Silent optional-dependency guard** — `notify/utils/uv.py:12-15`.
- Google-style docstrings, strict type hints, 120-column `black`.

### Known Risks / Gotchas

- **`typing.get_type_hints()` on `ProviderBase` methods will stop resolving
  `Actor`.** `from __future__ import annotations` prevents the *import-time*
  failure, but `get_type_hints` evaluates the string against module globals,
  and a module-level `__getattr__` does **not** rescue that lookup. The
  repository itself has zero `get_type_hints` callers, but `ProviderBase` is a
  public base class third parties subclass. *Mitigation*: this is an accepted,
  documented behaviour change — record it in `CHANGES.rst` and add a test that
  pins the new behaviour, so it is a decision rather than a surprise.
- **Undeclared direct imports.** `aiohttp`, `requests`, `aiofiles` and `redis`
  are imported directly by providers but declared **nowhere** in
  `pyproject.toml`; they arrive transitively today. Demoting `aiobotocore` out
  of core removes the only core-path supplier of `aiohttp`, which `dialpad`,
  `zoom` and `teams` import directly — **this feature would break them if
  `aiohttp` were not promoted into core**, which is why M2 adds it. `requests`
  (onesignal) and `aiofiles` (office365) still arrive transitively via their
  own extras and are left alone; `redis` is added to `azure` and `server`
  because both import it directly.
- **`uv.lock` drift.** Editing `pyproject.toml` alone is not enough — the lock
  still pins the old core set (`uv.lock:470-477`).
- **Cython rebuild.** `notify/exceptions.pyx` changes in M1. Every worktree
  needs `python setup.py build_ext --inplace` before tests, and again after
  editing the `.pyx`/`.pxd`. **Any import-cost measurement taken against stale
  or missing `.so` files is invalid** — rebuild first, then measure.
- **`notify/exceptions.pxd` is already out of sync** with the `.pyx`: it is
  missing `NotifyAuthError`. Do not be surprised by it, and do not silently
  "fix" it — M1 adds `ProviderDependencyError` to both files and leaves the
  pre-existing gap alone (out of scope; raise it separately if it matters).
- **`filterwarnings = ["error", ...]`** (`pyproject.toml:159-162`) — the
  `notify.templates` compatibility re-export must emit no warning at all, or
  the whole suite fails.
- **Memoisation hides failures across tests.** `PROVIDERS` is module-global; a
  provider loaded successfully by an earlier test will not be re-imported. The
  diagnostic tests must evict both `PROVIDERS[alias]` and
  `sys.modules["notify.providers.<alias>"]`.
- **The `notify` console script needs the `server` extra** after M2
  (`notify/__main__.py:4` imports `notify.server`). Document it; do not keep
  `cloudpickle` in core to avoid it.
- **This is an install-time breaking change.** Accepted by the user during
  proposal Q&A (U3) on condition of release notes — hence M4 is not optional.

### External Dependencies

| Package | Version | Reason |
|---|---|---|
| `aiohttp` | `>=3.10` | **promoted to core** — direct import of dialpad, zoom, teams; loses its transitive supplier when `aiobotocore` leaves core (installed: 3.14.3) |
| `redis` | `>=5.0` | added to `azure` + `server` — direct import of the O365 token store and the server (installed: 5.2.1) |
| `qworker` | `>=1.12.7` | moved into the new `server` extra (floor taken from the existing `all` entry) |
| `aiobotocore` | `>=2.15.2` | core → `ses` |
| `emoji` | `>=1.7.0` | core → `telegram` |
| `cloudpickle` | `>=3.1.0` | core → `server` |
| `pillow` | — | **removed entirely** — imported nowhere |

> The `aiohttp` and `redis` floors are proposed from the versions installed in
> this checkout; confirm them against CI's resolution before landing.

---

## 8. Open Questions

- [x] **How should `PROVIDER_EXTRAS` be sourced — hand-maintained or derived
      from `[project.optional-dependencies]`?** — *Resolved by the user,
      2026-09-29*: a hand-maintained literal dict in `notify/notify.py`.
      Reflected in §2 Data Models and the §3 M1 skeleton. Drift is covered by
      `test_provider_extras_names_exist_in_pyproject` (§4), which checks that
      every value names a real extra; a stronger bidirectional drift test was
      offered and declined.
- [x] **Several providers (twilio, xmpp, slack, office365) have no per-provider
      extra — what should the spec do?** — *Resolved by the user, 2026-09-29*:
      add per-provider extras. Reflected in §3 M2.
- [x] **Can `emoji` / `aiobotocore` / `pillow` / `cloudpickle` leave the core
      dependencies?** — *Resolved in the proposal Q&A (U3)*: yes, with release
      notes. Reflected in §3 M2 and M4.
- [ ] **Should the `~165 ms` outcome be enough to keep G6 in this feature?** —
      *Owner*: Jesus Lara.
      The proposal promised ~123 ms; re-measurement (§2) shows ~161-170 ms is
      the real ceiling while navconfig stays in the startup path. If the target
      was the number rather than the direction, G6 and M3 can be dropped from
      this feature without affecting G1-G5, and re-opened together with the
      navconfig work. *Decide before `/sdd-task`; the answer only adds or
      removes M3.*
- [ ] **Should `Notify("smtp")` keep the alias, or is `SMTP` the intended
      public name?** — *Owner*: Jesus Lara.
      §3 M1 fixes the alias so `Notify("smtp")` works, on the assumption that
      the lowercase factory alias is the public contract (it matches every
      other provider and the `notify/providers/smtp/` directory name). If
      instead the provider was deliberately not meant to be reachable by alias,
      say so and the fix becomes a clear error message instead.

---

## 9. Design Research Cross-Check

> Independent design opinion from the `codex` seat over the accepted exploration
> doc (never over this spec). Model: `gpt-5.6-luna` (codex-cli 0.157.0,
> `model_reasoning_effort=high`) · Status: completed · Duration: 4m44s ·
> Transcript: `sdd/state/FEAT-005/design_research/`
>
> **Acceptance note**: the proposal's frontmatter reads `status: review`, not
> `accepted`. The pass was run anyway because the user resolved all three of the
> proposal's open forks in-session and directed this spec to be built from it —
> acceptance in substance. Recorded here rather than by silently editing the
> proposal.
>
> All 10 `affected_paths` sets passed repository-containment and `test -e`.
> Every substantive claim was independently re-verified before triage; two
> (S4, S6) surfaced live defects the proposal had missed, and one (S10) rested
> partly on an evidence claim that did not check out.

| # | Suggestion (kind) | Disposition | Reason | Landed in |
|---|---|---|---|---|
| S1 | Make the import graph the measurable acceptance boundary (architecture) | CONFIRM | Matches the measured attribution; turns G6 from a vibe into a subprocess assertion | §2 Overview, §5 G6 |
| S2 | Use a clean subprocess for startup assertions (testing) | CONFIRM | Verified: `tests/test_jinja_string_templates.py:28` and `test_templates_integration.py` import jinja2 at collection time, so in-process `sys.modules` checks would be vacuous | §4 Integration Tests |
| S3 | Treat `Actor` annotation resolution as a compatibility contract (risk) | CONFIRM | Correct that PEP 562 cannot rescue `get_type_hints`. Repo has **zero** `get_type_hints` callers, so the break is accepted and documented rather than avoided | §7 Known Risks, §5 |
| S4 | Replace capitalize-based class lookup with export-aware resolution (api) | CONFIRM | **Reproduced**: `Notify("smtp")` → `ProviderError: module 'notify.providers.smtp' has no attribute 'Smtp'`. A live bug in the function M1 rewrites | §3 M1, §5 G2, §6 |
| S5 | Classify only genuine missing-SDK failures as extra errors (api) | CONFIRM | `ModuleNotFoundError.name` is the right discriminator; adopted as M1's fixed behavioural contract | §3 M1 |
| S6 | Define extras by factory alias, not class attribute (architecture) | CONFIRM | **Verified**: `Ses.provider == "amazon_ses"`, `Twilio.provider == "sms"`, `Aws.provider == "aws_email"`, `smtp` has no `provider` attribute. Keying on `cls.provider` would mis-key four of 17 | §2 Data Models, §6 table |
| S7 | Complete the migration as a server-aware lockfile change (risk) | CONFIRM | **Verified**: `uv.lock:470-477` still records the old core set, and `notify/server` imports `cloudpickle`/`qw`/`redis` with no `server` extra to hold them | §3 M2, §5 G3 |
| S8 | Add manifest and documentation parity checks (testing) | CONFIRM | `tests/test_office365_configuration.py` already parses `pyproject.toml`; extending that pattern is free | §4 Unit Tests |
| S9 | Make compiled-extension state part of the benchmark contract (testing) | CONFIRM | M1 edits `exceptions.pyx`, so a stale `.so` would silently invalidate the G6 measurement | §5 G6, §7 |
| S10 | Ship the install change with explicit migration notes (risk) | CONFIRM *(partial)* | Migration-notes recommendation adopted. Its supporting claim that "the README states Python 3.8" **did not verify** — the README states no Python version; `pyproject.toml:16` requires `>=3.11` | §3 M4 |

Summary: **10** confirmed (1 partial) · **0** rejected · **0** escalated.

---

## Worktree Strategy

- **Default isolation unit**: `per-spec` — one worktree,
  `.claude/worktrees/feat-FEAT-005-lazy-import-providers`, branched from
  `origin/dev`, tasks run sequentially.
- **Why not per-task**: M1 and M2 are logically independent but M1's messages
  cite M2's extra names and both are exercised by the same tests; splitting
  them across worktrees buys nothing and risks a mismatched pair landing.
- **Suggested order**: M2 → M1 → M3 → M5 → M4. M2 first because M1's messages
  and tests reference the extras it defines; M4 last because the README matrix
  is the output of M2.
- **Cross-feature dependencies**: none outstanding. FEAT-004
  (`mail-messages-graph`) is already merged into `dev` at `c96d632`; this spec's
  Codebase Contract was verified **after** that merge.
- **Before the first test run in the worktree**: `python setup.py build_ext --inplace`,
  then `PYTHONPATH=. pytest tests/ -v`.

---

## Revision History

| Version | Date | Author | Change |
|---|---|---|---|
| 0.1 | 2026-09-29 | Jesus Lara | Initial draft from FEAT-005 proposal; re-aimed per proposal Q&A; contract re-verified post-FEAT-004 merge; import-cost projection corrected (~123 ms → ~165 ms); S4/S6 defects folded in from design research |
