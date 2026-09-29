# TASK-37: Lock the dependency-diagnostics and provider-resolution contract

**Feature**: FEAT-005 — Actionable optional-dependency diagnostics and a slim core install
**Spec**: `sdd/specs/lazy-import-providers.spec.md`
**Status**: pending
**Priority**: high
**Estimated effort**: M (2-4h)
**Depends-on**: TASK-34
**Assigned-to**: unassigned

---

## Context

Implements the **M1 slice of spec §3 Module 5**, locking every claim goals **G1**
and **G2** make.

These are the tests that make TASK-34's behavioural contract real rather than
aspirational: that a missing SDK is a *different, catchable type* from a typo,
that the message is actionable, that a genuine bug inside a provider module is
never mislabelled as a missing dependency, and that `Notify("smtp")` — broken on
`dev` today — works.

---

## Scope

- Create `tests/test_provider_dependencies.py` with the `blocked_module` fixture
  and the seven M1 tests named in spec §4, plus a log-level assertion for AC-G1.

**NOT in scope**: `tests/test_dependency_manifest.py` (TASK-38),
`tests/test_startup_imports.py` (TASK-39), any change under `notify/` (TASK-34
owns the implementation — if a test fails, fix the code there, do not weaken the
test), and `tests/test_office365_configuration.py`, which must stay unmodified.

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `tests/test_provider_dependencies.py` | CREATE | The M1 test suite + `blocked_module` fixture |

---

## Codebase Contract (Anti-Hallucination)

> Verified against `dev` @ `d72fe6e` on 2026-09-29. Symbols marked **(TASK-34)**
> do not exist until that task lands — verify them before you start.

### Verified Imports

```python
from notify import Notify                                    # verified: notify/__init__.py:7
from notify.exceptions import ProviderError                  # verified: notify/notify.py:6
from notify.exceptions import ProviderDependencyError        # (TASK-34) — does not exist on dev
from notify.notify import PROVIDERS                          # verified: notify/notify.py:10
from notify.notify import LoadProvider                       # verified: notify/notify.py:70
from notify.notify import PROVIDER_EXTRAS, _known_providers  # (TASK-34)
from notify.providers.smtp import SMTP                       # verified: notify/providers/smtp/__init__.py:1
```

### Existing Signatures to Use

```python
# notify/notify.py
PROVIDERS = {}                                  # line 10 — module-global memo, keyed by alias
def LoadProvider(provider: str) -> type:        # line 70 — returns the CLASS, does not instantiate

# notify/providers/base.py
class ProviderBase(ABC):                        # line 31
```

### Test-suite facts

- `pytest.ini` is the **effective** config (pytest warns that it ignores
  `[tool.pytest.ini_options]` in `pyproject.toml`). It sets `asyncio_mode = auto`
  and `filterwarnings = ignore::DeprecationWarning`, and declares the markers
  `integration`, `live`, `real_llm`. **No other marker may be used** — and note
  that `--strict-markers` from `pyproject.toml` is inert, so an unknown marker
  fails silently rather than loudly.
- There is **no** `tests/conftest.py`. The `blocked_module` fixture lives in the
  new test file; do not create a conftest for it.
- `tests/test_office365_configuration.py` is the precedent for parsing
  `pyproject.toml` in a test (`tomllib`, module-level `PYPROJECT_PATH`).

### Provider aliases and their SDKs (spec §6 — for choosing what to block)

`telegram` → `aiogram` (the AC-G1 case). Others with a blockable SDK: `slack`
(`slack_bolt`), `twilio` (`twilio`), `xmpp` (`slixmpp`), `ses` (`aiobotocore`),
`onesignal` (`onesignal_sdk`), `gmail` (`gmail`), `office365`/`outlook`/`teams`
(`msal`, `msgraph`, …).

Aliases needing **no** third-party SDK — safe to resolve in any environment:
`aws`, `dummy`, `email`, `sendgrid`, `smtp`. (`dialpad` and `zoom` need `aiohttp`,
which TASK-33 puts in core.)

### Does NOT Exist

- ~~`tests/conftest.py`~~ — there is none.
- ~~a `blocked_module` fixture anywhere in `tests/`~~ — this task writes it.
- ~~`Smtp`~~ — the package exports `SMTP`.
- ~~`notify.providers.PROVIDERS`~~ — the registry is `notify.notify.PROVIDERS`.
- ~~a pytest marker other than `integration` / `live` / `real_llm`~~ — only those
  three are declared in `pytest.ini`.

---

## Implementation Notes

### The fixture is the hard part — memoisation hides failures

`PROVIDERS` is module-global and `sys.modules` caches the provider package. A
provider that any earlier test loaded successfully **will not be re-imported**, so
a naive block silently passes. The fixture must, for the duration of a test:

1. install a `sys.meta_path` finder that refuses the target module and its submodules,
2. evict `sys.modules["notify.providers.<alias>"]` **and** every `<sdk>*` entry,
3. evict `PROVIDERS[alias]`,

and undo all three afterwards — including restoring anything it evicted, or later
tests in the same session inherit a half-empty `sys.modules`.

### Blocking via `find_spec` raising vs. returning None

Spec §4's sketch **raises** `ImportError` from `find_spec`. That propagates as a
plain `ImportError`, **not** a `ModuleNotFoundError`, which is precisely the case
TASK-34 must *not* classify as a missing dependency — so a raising finder tests the
wrong branch. To simulate a genuinely absent package, `find_spec` must return
`None` for that name so the import machinery raises `ModuleNotFoundError` with
`.name` set. Reuse the raising variant **only** for
`test_internal_import_error_is_not_masked`, where a non-`ModuleNotFoundError`
`ImportError` is exactly what you want.

### Key Constraints

- Offline only: mock the transport, never reach a real service. No `integration`
  or `live` marker belongs in this file.
- Never instantiate a provider in `test_all_aliases_resolve_to_a_class` —
  constructors read credentials and open clients. `LoadProvider` returns the class;
  assert on the class.
- `test_all_aliases_resolve_to_a_class` can only resolve aliases whose SDK is
  installed. Skip an alias whose SDK is genuinely absent rather than failing —
  but **never** skip `smtp`, which is the AC-G2 case and needs nothing.
- Google-style docstrings, `black --line-length 120`.

---

## Implementation Blueprint

### Steps (in order)

1. Write the two finders and the `blocked_module` fixture — *why*: every
   diagnostic test depends on it, and its eviction logic is what makes the
   assertions non-vacuous.
2. Write the type-level tests (subclass, unknown provider, smtp) — *why*: they
   need no blocking and give a fast signal that TASK-34 landed.
3. Write the blocked-SDK tests — *why*: they are AC-G1 proper.
4. Write the propagation and log-level tests — *why*: they guard the two ways the
   rewrite could be subtly wrong while looking right.

### `tests/test_provider_dependencies.py` (CREATE)

```python
"""Provider resolution and optional-dependency diagnostics (FEAT-005, M1).

Locks spec §5 goals G1 (actionable missing-dependency diagnostics) and G2
(correct provider resolution via ``__all__``).
"""
import importlib
import importlib.abc
import logging
import sys

import pytest

from notify import Notify
from notify.exceptions import ProviderDependencyError, ProviderError
from notify.notify import PROVIDERS, LoadProvider, PROVIDER_EXTRAS, _known_providers


class _AbsentFinder(importlib.abc.MetaPathFinder):
    """Make a top-level module look genuinely absent.

    Returns ``None`` from :meth:`find_spec` so the import machinery falls
    through every finder and raises ``ModuleNotFoundError`` with ``.name``
    set — the discriminator ``LoadProvider`` keys on.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    def find_spec(self, fullname, path, target=None):
        if fullname == self.name or fullname.startswith(f"{self.name}."):
            return None
        return None  # never claims anything; see _install below


class _BrokenFinder(importlib.abc.MetaPathFinder):
    """Make a module raise a NON-ModuleNotFoundError ImportError."""

    def __init__(self, name: str) -> None:
        self.name = name

    def find_spec(self, fullname, path, target=None):
        if fullname == self.name or fullname.startswith(f"{self.name}."):
            raise ImportError(f"exploding import of {fullname!r}")
        return None


@pytest.fixture
def blocked_module(monkeypatch):
    """Make a top-level module unimportable for the duration of a test.

    Yields a callable ``block(sdk, alias)`` that evicts the provider package,
    the SDK's own modules and the ``PROVIDERS`` memo entry, then blocks the
    SDK. Everything is restored on teardown by ``monkeypatch``.
    """
    # FILL IN: implement `block(sdk, alias)`:
    #   1. monkeypatch.delitem(PROVIDERS, alias, raising=False)
    #   2. evict sys.modules entries equal to / under `notify.providers.<alias>`
    #      and equal to / under `sdk` (use monkeypatch.delitem so they restore)
    #   3. make the import of `sdk` fail with ModuleNotFoundError
    # Bounded by: the eviction requirement in spec §7 ("Memoisation hides
    # failures across tests") and by the finder note in Implementation Notes —
    # a genuinely-absent module must surface as ModuleNotFoundError with .name
    # set, NOT as a raised ImportError.
    raise NotImplementedError


def test_dependency_error_is_a_provider_error():
    """AC — existing ``except ProviderError`` handlers keep working."""
    assert issubclass(ProviderDependencyError, ProviderError)


def test_smtp_alias_resolves():
    """AC-G2 — fails on ``dev`` today: the package exports ``SMTP``, not ``Smtp``."""
    from notify.providers.smtp import SMTP

    assert isinstance(Notify("smtp"), SMTP)


def test_all_aliases_resolve_to_a_class():
    """AC-G2 — every package resolves via ``__all__``, without instantiating."""
    for alias in _known_providers():
        # FILL IN: assert isinstance(LoadProvider(alias), type). Skip an alias
        # whose SDK is genuinely not installed (catch ProviderDependencyError ->
        # pytest.skip), but NEVER skip "smtp" — bounded by AC-G2.
        raise NotImplementedError


def test_missing_sdk_raises_dependency_error(blocked_module):
    """AC-G1 — the message names both the SDK and the install command."""
    blocked_module("aiogram", "telegram")
    with pytest.raises(ProviderDependencyError) as excinfo:
        Notify("telegram")
    message = str(excinfo.value)
    assert "aiogram" in message
    assert "async-notify[telegram]" in message


def test_unknown_provider_raises_provider_error():
    """AC-G1 — a typo is a different type from a missing SDK."""
    with pytest.raises(ProviderError) as excinfo:
        Notify("does_not_exist")
    assert not isinstance(excinfo.value, ProviderDependencyError)
    # FILL IN: assert the message lists known aliases — bounded by AC-G1
    # ("the message lists known aliases"). Check for at least one alias that
    # needs no SDK, e.g. "dummy".
    raise NotImplementedError


def test_notify_factory_preserves_error_subclass(blocked_module):
    """AC-G1 — ``Notify.__new__`` and ``Notify.provider`` must not flatten it."""
    # FILL IN: block aiogram/telegram, then assert BOTH entry points raise
    # ProviderDependencyError — Notify("telegram") and
    # Notify.provider("telegram"). Bounded by spec §2 ("both must re-raise a
    # ProviderError unchanged"); TASK-34 edits two identical except blocks and
    # missing one is the expected failure mode.
    raise NotImplementedError


def test_internal_import_error_is_not_masked():
    """AC-G1 — a non-ModuleNotFoundError ImportError propagates unchanged."""
    # FILL IN: install _BrokenFinder for a provider's SDK, evict the provider
    # module and its PROVIDERS entry, then assert the raised exception is an
    # ImportError that is NOT a ModuleNotFoundError and NOT a
    # ProviderDependencyError, with its __cause__/type intact. Bounded by spec
    # §3 M1 ("propagates with its original type and __cause__ intact. It must
    # never be reported as a missing dependency").
    raise NotImplementedError


def test_neither_path_logs_at_critical(blocked_module, caplog):
    """AC-G1 — "Neither path logs at CRITICAL"."""
    # FILL IN: with caplog.at_level(logging.DEBUG), trigger both the unknown-
    # provider and the missing-SDK paths, then assert no record has
    # levelno >= logging.CRITICAL. Bounded by AC-G1 and by spec §3 M1's
    # "log the failure at `error`, not `critical`".
    raise NotImplementedError
```
**Why this shape**: the file follows spec §4's M1 table one-for-one, plus the
CRITICAL assertion AC-G1 requires but §4's table omits. `_AbsentFinder` and
`_BrokenFinder` are separate classes on purpose — they exercise the two branches
TASK-34 must keep apart, and collapsing them into one parameterised finder is how
that distinction gets lost. Assertions are on the **message substring**
`async-notify[telegram]`, not on a full-message equality, so TASK-34 keeps freedom
over wording while AC-G1's substance stays pinned.

> Note on `_AbsentFinder`: a `MetaPathFinder` returning `None` does not itself
> block anything — it just declines. To make a module genuinely absent you must
> also remove the real finders' ability to serve it (evict from `sys.modules` and
> make `sys.meta_path` refuse), which is what the fixture's `FILL IN` covers.
> Verify your fixture actually produces `ModuleNotFoundError` before trusting any
> test that uses it: a fixture that silently fails to block turns every AC-G1
> assertion green for the wrong reason.

### FILL IN checklist

- [ ] `blocked_module` — eviction + blocking; must yield a real
      `ModuleNotFoundError` with `.name` set; bounded by spec §7's memoisation note.
- [ ] `test_all_aliases_resolve_to_a_class` — resolve-not-instantiate, skip absent
      SDKs, never skip `smtp`; AC-G2.
- [ ] `test_unknown_provider_raises_provider_error` — assert aliases are listed; AC-G1.
- [ ] `test_notify_factory_preserves_error_subclass` — cover **both** entry points; spec §2.
- [ ] `test_internal_import_error_is_not_masked` — original type and `__cause__`; spec §3 M1.
- [ ] `test_neither_path_logs_at_critical` — no record at CRITICAL; AC-G1.

---

## Acceptance Criteria

- [ ] All eight tests exist and pass:
      `PYTHONPATH=. pytest tests/test_provider_dependencies.py -v`
- [ ] The `blocked_module` fixture demonstrably produces `ModuleNotFoundError`
      (assert it directly in the fixture or in a dedicated sanity test) — a fixture
      that fails to block makes every G1 assertion vacuous.
- [ ] Tests leave `sys.modules` and `PROVIDERS` exactly as they found them:
      the full suite passes in **both** orders —
      `PYTHONPATH=. pytest tests/ -v` and
      `PYTHONPATH=. pytest tests/test_provider_dependencies.py tests/ -v`.
- [ ] No test reaches a real external service; no `integration` / `live` marker.
- [ ] `tests/test_office365_configuration.py` is untouched and still passes.
- [ ] `black --line-length 120`, `flake8`, `pylint` clean on the new file.

---

## Test Specification

This task *is* the test specification — spec §4's M1 rows, reproduced:

| Test | Asserts |
|---|---|
| `test_missing_sdk_raises_dependency_error` | `aiogram` blocked ⇒ `ProviderDependencyError`; message has `aiogram` + `async-notify[telegram]` |
| `test_unknown_provider_raises_provider_error` | `ProviderError` but **not** `ProviderDependencyError`; lists aliases |
| `test_dependency_error_is_a_provider_error` | `issubclass(ProviderDependencyError, ProviderError)` |
| `test_notify_factory_preserves_error_subclass` | Neither `Notify()` nor `Notify.provider()` flattens the subclass |
| `test_smtp_alias_resolves` | `Notify("smtp")` is an `SMTP` instance |
| `test_all_aliases_resolve_to_a_class` | Every package resolves via `__all__`, uninstantiated |
| `test_internal_import_error_is_not_masked` | Non-`ModuleNotFoundError` `ImportError` propagates unchanged |
| `test_neither_path_logs_at_critical` | No CRITICAL record on either path |

Run:
```bash
source .venv/bin/activate
python setup.py build_ext --inplace
PYTHONPATH=. pytest tests/test_provider_dependencies.py -v
```

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** §3 Module 1, §4 and §5 (G1/G2).
2. **Check dependencies** — TASK-34 must be in `sdd/tasks/completed/`, and the
   Cython extension must be rebuilt (`python setup.py build_ext --inplace`) or
   `ProviderDependencyError` will not import.
3. **Verify the Codebase Contract** — confirm `ProviderDependencyError`,
   `PROVIDER_EXTRAS` and `_known_providers` exist with the shapes listed.
4. Update this feature's index entry to `in-progress`.
5. **Implement** from the blueprint; resolve every `FILL IN`. If a test fails,
   fix `notify/` — never weaken the assertion to match the code.
6. **Verify** every acceptance criterion, including both suite orderings.
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
