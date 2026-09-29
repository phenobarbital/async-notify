# TASK-34: Actionable dependency diagnostics and export-aware provider resolution

**Feature**: FEAT-005 — Actionable optional-dependency diagnostics and a slim core install
**Spec**: `sdd/specs/lazy-import-providers.spec.md`
**Status**: pending
**Priority**: high
**Estimated effort**: L (4-8h)
**Depends-on**: TASK-33
**Assigned-to**: unassigned

---

## Context

Implements **spec §3 Module 1**, serving goals **G1** and **G2**.

Today a missing optional SDK is indistinguishable from a typo: with `aiogram`
blocked, `Notify("telegram")` and `Notify("does_not_exist")` both raise a flat
`ProviderError` logged at CRITICAL, and neither names the extra to install. The
only discriminator is buried in a chained `ModuleNotFoundError`.

The same function carries two live defects found during research and confirmed
by the independent design review (spec §9, S4 and S6):

- **`Notify("smtp")` is broken.** `getattr(module, provider.capitalize())` asks
  for `Smtp`; the package exports `SMTP`. Reproduced on `dev`.
- **The `except ImportError` fallback is dead code** — it re-imports the classpath
  that just failed and, on success, would return the *module* instead of the class.

Depends on TASK-33 because the messages this task emits cite extra names that
TASK-33 defines.

---

## Scope

- Add `ProviderDependencyError(ProviderError)` to `notify/exceptions.pyx` **and**
  `notify/exceptions.pxd`.
- Add the hand-maintained `PROVIDER_EXTRAS` literal to `notify/notify.py`.
- Add module-private `_known_providers()`.
- Rewrite `LoadProvider` — same signature, same memoisation contract — around
  `ModuleNotFoundError.name` as the sole discriminator, resolving the class
  through the package's `__all__`.
- Make `Notify.__new__` and `Notify.provider` re-raise `ProviderError` and its
  subclasses **unchanged**, and log at `error` rather than `critical`.

**NOT in scope**: `notify/providers/base.py`, `notify/templates.py` or
`notify/utils/templates.py` (TASK-35 owns those); `pyproject.toml` (TASK-33);
the new test files (TASK-37). Do **not** touch the pre-existing `.pxd` drift —
`NotifyAuthError` is missing from `notify/exceptions.pxd` and spec §7 says to
leave it alone. Do **not** add a `ProviderBase.provider_extra` attribute.

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `notify/exceptions.pyx` | MODIFY | Add `ProviderDependencyError` |
| `notify/exceptions.pxd` | MODIFY | Mirror the declaration |
| `notify/notify.py` | MODIFY | `PROVIDER_EXTRAS`, `_known_providers`, rewritten `LoadProvider`, error re-raise |

---

## Codebase Contract (Anti-Hallucination)

> Verified against `dev` @ `d72fe6e` on 2026-09-29.

### Verified Imports

```python
import importlib                                              # verified: notify/notify.py:1
from navconfig.logging import logger                          # verified: notify/notify.py:3
from .exceptions import NotifyException, ProviderError        # verified: notify/notify.py:6
from .providers.base import ProviderBase                      # verified: notify/notify.py:7
```

### Existing Signatures to Use

```python
# notify/notify.py
PROVIDERS = {}                                                # line 10
_TEMPLATE_ENV: TemplateParser | None = None                   # line 15

class Notify:
    def __new__(cls: type['ProviderBase'], provider: str, *args, **kwargs):   # line 31
        # lines 42-48: `except Exception as ex:` -> logger.critical(...) ->
        #              raise ProviderError(message=f"Cannot Load provider {provider}: {ex}") from ex
    @classmethod
    def provider(cls: type['ProviderBase'], provider: str, *args, **kwargs):  # line 51
        # lines 61-67: identical wrapping

def LoadProvider(provider: str):                              # line 70
    classpath = f"notify.providers.{provider}"                # line 76
    module = importlib.import_module(classpath, package="providers")   # line 77
    return getattr(module, provider.capitalize())             # line 78  <- the smtp bug
    # except ImportError: __import__(classpath, fromlist=[provider]); return obj   # 79-82 (DEAD)
    # raise NotifyException(f"Error: No Provider {provider} was Found: {exc}")     # 84-86

def __getattr__(name: str):                                   # line 89 — leave alone (TASK-35 edits it)
def __dir__() -> list[str]:                                   # line 119

# notify/exceptions.pyx
cdef class NotifyException(Exception):                        # line 5
    def __init__(self, str message, int code = 0, str payload = None, **kwargs)   # line 10
cdef class ProviderError(NotifyException):                    # line 30
cdef class NotifyAuthError(ProviderError):                    # line 45  (LAST class in the file)

# notify/exceptions.pxd
cdef class ProviderError(NotifyException):                    # line 13
cdef class NotifyTimeout(ProviderError):                      # line 25  (LAST class in the file)
```

### Provider → extra map, verified by AST scan (spec §6 table)

Every package under `notify/providers/` exports exactly **one** name via
`__all__` — verified by reading all 17 `__init__.py` files. `smtp` exports
`"SMTP"`; `telegram` imports from `.Telegram` (capital T) but still exports
`"Telegram"`.

Aliases that need an extra (all others carry **no** entry):

| alias | extra | | alias | extra |
|---|---|---|---|---|
| `gmail` | `google` | | `ses` | `ses` |
| `office365` | `azure` | | `slack` | `slack` |
| `outlook` | `azure` | | `telegram` | `telegram` |
| `onesignal` | `push` | | `twilio` | `twilio` |
| `teams` | `azure` | | `xmpp` | `xmpp` |

No entry for: `aws`, `dialpad`, `dummy`, `email`, `sendgrid`, `smtp`, `zoom`
(no third-party SDK, or `aiohttp` which TASK-33 puts in core).

### Does NOT Exist

- ~~`notify.exceptions.ProviderDependencyError`~~ — **this task creates it**.
- ~~`ProviderBase.provider_extra`~~ / ~~`ProviderBase.required_packages`~~ — no such
  attribute; the map is keyed by alias, not by class. Do not add one.
- ~~keying `PROVIDER_EXTRAS` by `cls.provider`~~ — it disagrees with the alias for
  four providers: `Ses.provider == "amazon_ses"`, `Twilio.provider == "sms"`,
  `Aws.provider == "aws_email"`, and `smtp` has **no** `provider` attribute.
- ~~`Smtp`~~ — the package exports `SMTP` (`notify/providers/smtp/__init__.py:3`).
- ~~`notify.providers.registry`~~ / ~~`notify.providers.PROVIDERS`~~ — the registry is
  `PROVIDERS` in `notify/notify.py:10` and nowhere else.
- ~~exports on `notify/providers/__init__.py`~~ — it is a bare docstring.
- ~~`NotifyAuthError` in `notify/exceptions.pxd`~~ — pre-existing drift. Leave it.

---

## Implementation Notes

### Pattern to Follow

`notify/providers/telegram/Telegram.py:341-348` already does "deferred import +
a message naming the extra". **Generalise that message shape; do not invent a
new one.** `notify/utils/uv.py:12-15` is the silent-optional-guard precedent.

### Behavioural contract — fixed by spec §3 M1, not renegotiable

- Discrimination is on `ModuleNotFoundError.name` **only**. A missing name equal
  to or starting with `notify.providers.` ⇒ unknown provider ⇒ `ProviderError`.
  Any other missing name ⇒ `ProviderDependencyError`.
- An `ImportError` that is **not** a `ModuleNotFoundError`, and any other
  exception raised while importing the provider module, propagates with its
  original type and `__cause__` intact. It must never become a dependency error.
- Class resolution: take the single name in the package's `__all__`. If `__all__`
  is absent or does not resolve, raise `ProviderError` naming the package.
  **No `.capitalize()` fallback.**
- `PROVIDERS` memoisation semantics unchanged; failures are **not** cached.
- Both `Notify` entry points log at `error`, not `critical` — the exception
  already reaches the caller, so CRITICAL double-reports a recoverable,
  user-caused condition (AC-G1).

### Key Constraints

- **Cython rebuild is mandatory**: `python setup.py build_ext --inplace` after every
  `.pyx`/`.pxd` edit, before running any test. Generated `.c`/`.so` are untracked.
- `ProviderDependencyError` must subclass `ProviderError` so existing
  `except ProviderError` handlers keep working (AC, spec §5).
- Google-style docstrings, strict type hints, `black --line-length 120`.
- `_known_providers()` must **never import a provider module** — it only lists
  directories.

---

## Implementation Blueprint

### Steps (in order)

1. Add `ProviderDependencyError` to the `.pyx`, then mirror it in the `.pxd` —
   *why*: other modules `cimport` from the `.pxd`; a missing mirror breaks them.
2. Rebuild the extension — *why*: `notify/notify.py` imports the new class at
   module level, so nothing else in this task can even be imported until the
   `.so` carries it.
3. Add `PROVIDER_EXTRAS` and `_known_providers()` to `notify/notify.py` — *why*:
   `LoadProvider` reads both, so they must exist before it is rewritten.
4. Rewrite `LoadProvider` — *why*: it is the single place where G1's
   discrimination and G2's `__all__` resolution both live.
5. Change both `Notify` entry points' `except` clauses — *why*: they currently
   catch `Exception` and re-raise a flat `ProviderError`, which would erase the
   new subclass and defeat G1 entirely.
6. Rebuild again, then smoke-test `Notify("smtp")` — *why*: AC-G2 is the one
   criterion that fails on `dev` today, so it is the proof the rewrite landed.

### `notify/exceptions.pyx` (MODIFY)

```cython
# occurrences: 1 (verified: grep -c 'cdef class NotifyAuthError(ProviderError):' notify/exceptions.pyx)
# AFTER — append at end of file, below `cdef class NotifyAuthError(ProviderError):`
# and its docstring (verified: notify/exceptions.pyx:45-46)

cdef class ProviderDependencyError(ProviderError):
    """Raised when a provider's optional third-party SDK is missing.

    Distinguishes "this provider needs a package you have not installed"
    from "this provider does not exist", which ``ProviderError`` alone
    cannot express. Subclasses :class:`ProviderError`, so existing
    ``except ProviderError`` handlers keep working unchanged.
    """
```
**Why this shape**: spec §2 "New Public Interfaces" fixes the name and the base
class. It adds no `__init__` — it inherits `NotifyException.__init__(str message,
int code = 0, str payload = None, **kwargs)`, so callers construct it with
`message=...` exactly like `ProviderError`. Do not give it its own constructor.

### `notify/exceptions.pxd` (MODIFY)

```cython
# occurrences: 1 (verified: grep -c 'cdef class NotifyTimeout(ProviderError):' notify/exceptions.pxd)
# AFTER — append at end of file, below the `NotifyTimeout` block
# (verified: notify/exceptions.pxd:25-27)

cdef class ProviderDependencyError(ProviderError):
    """Raised when a provider's optional third-party SDK is missing."""
    pass
```
**Why**: the `.pxd` must stay in sync with the `.pyx` or other modules cannot
`cimport` the class. Match the file's existing style — docstring plus `pass`.
Do **not** also add the missing `NotifyAuthError` here; spec §7 scopes that out.

### `notify/notify.py` (MODIFY — imports)

```python
# occurrences: 1 (verified: grep -c 'from .exceptions import NotifyException, ProviderError' notify/notify.py)
# REPLACE (verified: notify/notify.py:6)
from .exceptions import ProviderDependencyError, ProviderError
```
**Why**: `NotifyException` was raised only by the dead fallback this task deletes.
If anything else in the file still references it after your rewrite, keep the
import instead of leaving a `NameError` — verify with
`grep -n NotifyException notify/notify.py` before committing.

### `notify/notify.py` (MODIFY — module constants)

```python
# occurrences: 1 (verified: grep -c '^PROVIDERS = {}' notify/notify.py)
# AFTER — insert below `PROVIDERS = {}` (verified: notify/notify.py:10)

PROVIDER_EXTRAS: dict[str, str] = {
    "gmail": "google",
    "office365": "azure",
    "onesignal": "push",
    "outlook": "azure",
    "ses": "ses",
    "slack": "slack",
    "teams": "azure",
    "telegram": "telegram",
    "twilio": "twilio",
    "xmpp": "xmpp",
}
"""Factory alias -> ``pyproject.toml`` extra that ships its SDK.

Keyed by the package directory name under ``notify/providers/`` — i.e. the
string callers pass to :class:`Notify` — never by ``cls.provider``, which
disagrees for ses/twilio/aws (verified: notify/providers/ses/ses.py,
notify/providers/twilio/twilio.py, notify/providers/aws/aws.py). Providers
whose only dependencies are core carry no entry.
"""
```
**Why this shape**: spec §8 records the user's decision — a hand-maintained
literal, not derived from package metadata at runtime. The 10 entries are exactly
the aliases whose SDK ships in an extra (spec §6 table); the other seven need no
entry and `LoadProvider` must degrade gracefully when the lookup misses.
TASK-38's `test_provider_extras_names_exist_in_pyproject` asserts every **value**
is a real extra key, so these must match TASK-33's names exactly.

### `notify/notify.py` (MODIFY — LoadProvider and its helper)

```python
# occurrences: 1 (verified: grep -c '^def LoadProvider(provider: str):' notify/notify.py)
# REPLACE the entire function, lines 70-86 (verified: notify/notify.py:70)

def _known_providers() -> tuple[str, ...]:
    """Return the sorted factory aliases discoverable on disk.

    Used only to build the "unknown provider" message. Never imports a
    provider module — it lists directories under ``notify/providers/``.

    Returns:
        Sorted package directory names, excluding private/dunder entries.
    """
    # FILL IN: list the child directories of Path(__file__).parent / "providers"
    # that contain an __init__.py and do not start with "_" — bounded by
    # "never imports a provider module" (spec §3 M1) and AC-G1's
    # "message lists known aliases". Return a sorted tuple.
    raise NotImplementedError


def LoadProvider(provider: str) -> type:
    """Dynamically load a Notify provider class by factory alias.

    Args:
        provider: Factory alias, i.e. the package directory name under
            ``notify/providers/`` (e.g. ``"telegram"``, ``"smtp"``).

    Returns:
        The provider class exported by ``notify.providers.<provider>``,
        resolved through that package's ``__all__``.

    Raises:
        ProviderDependencyError: The provider module exists but a third-party
            module it imports is missing. The message names the missing module
            and, when known, the extra that ships it.
        ProviderError: No such provider, or the package exports no resolvable
            provider class. The message lists known aliases.
    """
    classpath = f"notify.providers.{provider}"
    try:
        module = importlib.import_module(classpath)
    except ModuleNotFoundError as exc:
        missing = exc.name or ""
        if missing == classpath or missing.startswith(f"{classpath}."):
            # FILL IN: raise ProviderError naming `provider` and listing
            # _known_providers() — bounded by AC-G1 ("lists known aliases").
            raise NotImplementedError from exc
        # FILL IN: build the dependency message from `missing` and
        # PROVIDER_EXTRAS.get(provider); when an extra is known it MUST contain
        # the literal `pip install async-notify[<extra>]`. Raise
        # ProviderDependencyError(message=...) from exc — bounded by AC-G1
        # ("names both aiogram and pip install async-notify[telegram]") and by
        # the telegram precedent at notify/providers/telegram/Telegram.py:341-348.
        raise NotImplementedError from exc

    exported = getattr(module, "__all__", None)
    # FILL IN: resolve the single name in `exported` via getattr(module, name).
    # If `exported` is missing/empty, or the name does not resolve, raise
    # ProviderError naming `classpath` — bounded by spec §3 M1 ("Do NOT fall
    # back to .capitalize()") and AC-G2.
    raise NotImplementedError
```
**Why this shape**: the `try` wraps **only** `import_module`, so a
`ModuleNotFoundError` raised later by class resolution can never be misread as a
missing SDK. Catching `ModuleNotFoundError` (not `ImportError`) is what lets a
non-`ModuleNotFoundError` `ImportError` propagate untouched, which AC-G1 requires
and TASK-37 asserts. `exc.name` is the whole discriminator — do not also inspect
the message string. Note `package="providers"` is dropped from the
`import_module` call: it was inert for an absolute classpath.

### `notify/notify.py` (MODIFY — both Notify entry points)

```python
# occurrences: 2 (verified: grep -c 'raise ProviderError(' notify/notify.py)
# Two IDENTICAL except blocks — __new__ at lines 42-48 and provider() at 61-67.
# Apply the SAME edit to BOTH; quote the surrounding `def` line to tell them apart.
# BEFORE (both):
#     except Exception as ex:
#         logger.critical(f"Cannot Load provider {provider}: {ex}")
#         raise ProviderError(message=f"Cannot Load provider {provider}: {ex}") from ex
# AFTER (both):
    except ProviderError:
        # Already precise (including ProviderDependencyError) — re-raise
        # unchanged so the subclass survives to the caller.
        raise
    except Exception as ex:
        logger.error(f"Cannot Load provider {provider}: {ex}")
        raise ProviderError(
            message=f"Cannot Load provider {provider}: {ex}"
        ) from ex
```
**Why**: without the first clause, `except Exception` flattens
`ProviderDependencyError` into a plain `ProviderError` and G1 is defeated at the
last step — spec §2 calls this out explicitly. The bare `raise` preserves the
original traceback and `__cause__`. The `critical` → `error` downgrade is
AC-G1's "neither path logs at CRITICAL". There are **two** such blocks; missing
one leaves `Notify.provider()` broken while `Notify()` works.

### FILL IN checklist

- [ ] `_known_providers()` — directory listing, no imports; bounded by spec §3 M1.
- [ ] `LoadProvider` unknown-provider branch — `ProviderError` listing known aliases; AC-G1.
- [ ] `LoadProvider` dependency branch — message names the missing module **and**
      `pip install async-notify[<extra>]` when the extra is known; AC-G1.
- [ ] `LoadProvider` class resolution — single `__all__` name, `ProviderError` on
      failure, no `.capitalize()`; AC-G2.

---

## Acceptance Criteria

- [ ] `issubclass(ProviderDependencyError, ProviderError)` is `True`, and the class
      is present in both `notify/exceptions.pyx` and `notify/exceptions.pxd`.
- [ ] `python setup.py build_ext --inplace` succeeds and
      `from notify.exceptions import ProviderDependencyError` works.
- [ ] With `aiogram` blocked, `Notify("telegram")` raises `ProviderDependencyError`
      and the message contains both `aiogram` and `async-notify[telegram]`. *(AC-G1)*
- [ ] `Notify("does_not_exist")` raises `ProviderError` but **not**
      `ProviderDependencyError`, and the message lists known aliases. *(AC-G1)*
- [ ] A non-`ModuleNotFoundError` `ImportError` inside a provider module propagates
      with its original type and `__cause__`. *(AC-G1)*
- [ ] Neither path logs at CRITICAL. *(AC-G1)*
- [ ] `Notify("smtp")` returns an `SMTP` instance. *(AC-G2 — fails on `dev` today)*
- [ ] Every package under `notify/providers/` resolves to a class via `__all__`. *(AC-G2)*
- [ ] `PROVIDERS` memoisation unchanged; a failed load is not cached.
- [ ] `notify.__all__` unchanged; `except ProviderError` still catches every load failure.
- [ ] `PYTHONPATH=. pytest tests/ -v` passes (after `build_ext --inplace`).
- [ ] `black --line-length 120`, `flake8`, `pylint` clean on the changed files.

---

## Test Specification

TASK-37 writes the full suite in `tests/test_provider_dependencies.py`. Use this
scaffold to self-verify before handing off:

```python
import pytest
from notify import Notify
from notify.exceptions import ProviderDependencyError, ProviderError


def test_dependency_error_is_a_provider_error():
    assert issubclass(ProviderDependencyError, ProviderError)


def test_smtp_alias_resolves():
    """AC-G2 — fails on dev today."""
    from notify.providers.smtp import SMTP
    assert isinstance(Notify("smtp"), SMTP)


def test_unknown_provider_raises_provider_error():
    with pytest.raises(ProviderError) as ei:
        Notify("does_not_exist")
    assert not isinstance(ei.value, ProviderDependencyError)


def test_all_aliases_resolve_to_a_class():
    """Resolve every alias WITHOUT instantiating it."""
    from notify.notify import LoadProvider, _known_providers
    for alias in _known_providers():
        assert isinstance(LoadProvider(alias), type), alias
```

> `test_all_aliases_resolve_to_a_class` only passes with every extra installed.
> Run it as `uv sync --extra all` or accept skips for uninstalled SDKs — decide
> in TASK-37, not here.

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** §3 Module 1, §5 (G1/G2), §6 and §7.
2. **Check dependencies** — TASK-33 must be in `sdd/tasks/completed/`; the extra
   names in `PROVIDER_EXTRAS` must match the manifest it landed.
3. **Verify the Codebase Contract** — re-read `notify/notify.py:1-90`,
   `notify/exceptions.pyx` and `notify/exceptions.pxd` before editing.
4. Update this feature's index entry to `in-progress`.
5. **Implement** from the blueprint; resolve every `FILL IN`. Rebuild the Cython
   extension before you run anything.
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

### Completion Note
Added ProviderDependencyError (.pyx + .pxd), PROVIDER_EXTRAS, _known_providers, rewritten LoadProvider (ModuleNotFoundError.name discriminator, `__all__` resolution), and both Notify entry points re-raise ProviderError unchanged and log at error. Notify("smtp") now returns SMTP; blocked-aiogram telegram raises ProviderDependencyError naming `async-notify[telegram]` (message cites the missing module, e.g. `aiogram.client`). Full suite: 329 passed; 2 test_ses failures are pre-existing on dev (botocore).
KNOWN ISSUE (out of scope, pre-existing): `notify/providers/onesignal/onesignal.py` imports `ProviderIMBase`, which does not exist in providers/base.py, so LoadProvider("onesignal") raises a raw ImportError (propagates by design). Task AC "every package resolves via __all__" therefore cannot hold for onesignal until that is fixed.
