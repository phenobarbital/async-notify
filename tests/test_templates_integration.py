"""Offline integration suite for FEAT-002 (TemplateParser refactor).

Covers the four integration tests enumerated in
``sdd/specs/templateparser-refactor.spec.md`` §4 "Integration Tests",
proving the two seams the refactor actually moved:

  - The lazy ``notify.notify.TemplateEnv`` singleton (TASK-010): not built
    at import, memoised on first access, and tolerant of a missing
    ``TEMPLATE_DIR``.
  - The provider render path (unchanged by this feature):
    ``ProviderBase.__init__`` (``notify/providers/base.py:66-67``) and
    ``self._tpl.get_template()`` (``notify/providers/base.py:142``) stay
    byte-identical to 1.5.7.

``tests/test_templates.py`` (TASK-012) covers ``TemplateParser`` in
isolation; this module never constructs a ``TemplateParser`` directly
except through the lazy singleton or a hermetic swap-in. Reload-based
tests carefully save and restore ``sys.modules["notify.notify"]`` so they
do not leak state into the rest of the session, regardless of whether this
file runs first, last, or in isolation.
"""
import importlib
import sys
from pathlib import Path

import pytest

from notify.notify import (
    TemplateEnv as _initial_template_env,  # noqa: F401  (forces one build)
)
from notify.providers.base import ProviderBase, ProviderType
from notify.templates import TemplateParser


class _DummyProvider(ProviderBase):
    """Minimal concrete provider — no transport, no credentials.

    Every provider under ``notify/providers/`` reaches for real
    credentials or transports, so a local test double is used to exercise
    ``ProviderBase.__init__`` / ``_prepare_`` without either.
    """

    provider = "dummy"
    provider_type = ProviderType.NOTIFY
    blocking = False

    async def connect(self, *args, **kwargs):
        return None

    async def close(self):
        return None

    async def _send_(self, to, message, subject=None, **kwargs):
        return message


def _reimport_notify_notify():
    """Force a fresh re-execution of ``notify/notify.py``'s module body.

    Returns the freshly imported module. Callers MUST restore state
    afterwards via :func:`_restore_notify_notify` so other tests in the
    same session keep using a consistent, already-memoised singleton.
    """
    sys.modules.pop("notify.notify", None)
    return importlib.import_module("notify.notify")


def _restore_notify_notify(original_module) -> None:
    """Undo :func:`_reimport_notify_notify`.

    Restoring ``sys.modules["notify.notify"]`` alone is NOT enough:
    ``import notify.notify as nn`` resolves through the parent package's
    ``notify.notify`` attribute (set as a side effect of the import
    machinery whenever a submodule is (re)imported), not purely through
    ``sys.modules``. Both must be repointed at the original module or
    later tests in the same session silently observe a stale, orphaned
    ``TemplateEnv`` singleton.
    """
    sys.modules.pop("notify.notify", None)
    if original_module is not None:
        sys.modules["notify.notify"] = original_module
        import notify as _notify_pkg
        _notify_pkg.notify = original_module


def test_template_env_lazy_not_built_on_import(monkeypatch):
    """Importing ``notify.notify`` must not construct a ``TemplateParser`` (spec §7 R5)."""
    calls = []
    original_init = TemplateParser.__init__

    def counting_init(self, *args, **kwargs):
        calls.append(1)
        return original_init(self, *args, **kwargs)

    monkeypatch.setattr(TemplateParser, "__init__", counting_init)

    original_module = sys.modules.get("notify.notify")
    try:
        module = _reimport_notify_notify()
        assert "TemplateEnv" not in vars(module)  # not eagerly bound
        assert calls == []                        # nothing built at import time
    finally:
        _restore_notify_notify(original_module)


def test_template_env_memoised():
    """Two ``TemplateEnv`` accesses return the identical object."""
    import notify.notify as nn

    env1 = nn.TemplateEnv
    env2 = nn.TemplateEnv
    assert env1 is env2
    assert isinstance(env1, TemplateParser)


def test_import_notify_without_templates_dir(monkeypatch, tmp_path: Path):
    """With ``TEMPLATE_DIR`` pointing at a nonexistent path, re-importing
    ``notify.notify`` succeeds (no ``RuntimeError``), and the lazily-built
    ``TemplateEnv`` degrades to memory-only mode.

    Scoped to ``notify.notify`` rather than the top-level ``notify``
    package: that is exactly the module the pre-refactor eager-construction
    block lived in (``notify/notify.py:83-87``), and the only one whose
    behaviour this feature changed. Reloading the top-level ``notify``
    package would also re-run unrelated import-time side effects (uvloop
    policy installation) for no additional coverage.
    """
    missing = tmp_path / "does-not-exist"
    monkeypatch.setattr("notify.conf.TEMPLATE_DIR", missing)

    original_module = sys.modules.get("notify.notify")
    try:
        module = _reimport_notify_notify()
        # The import itself must not raise. Accessing TemplateEnv triggers
        # the lazy build and must degrade to memory-only mode, not raise.
        env = module.TemplateEnv
        assert env.path is None
    finally:
        _restore_notify_notify(original_module)


@pytest.mark.asyncio
async def test_provider_base_get_template_still_works(tmp_path: Path):
    """A ``ProviderBase`` subclass resolves a template via ``self._tpl.get_template()``.

    First proves the ``ProviderBase.__init__`` seam
    (``notify/providers/base.py:66-67``) still wires ``self._tpl`` from the
    lazy ``TemplateEnv`` singleton, then swaps in a hermetic
    ``TemplateParser`` (built under ``tmp_path``) to exercise
    ``get_template()`` deterministically and offline.

    Deliberately an ``async def`` test: ``ProviderBase.__init__`` falls
    back to the deprecated, ambient-state-dependent
    ``asyncio.get_event_loop()`` when no loop is already running
    (``notify/providers/base.py:54-57``), which becomes unreliable once
    another test in the suite has closed/replaced the global loop (a
    pre-existing suite fragility, unrelated to this feature — see
    ``tests/test_outlook1.py``). Running inside a ``pytest-asyncio``
    event loop keeps construction on the primary, reliable
    ``asyncio.get_running_loop()`` path, matching the house style in
    ``tests/test_email_utf8.py``. The final render is done through a
    hermetic parser built with ``enable_async=False``, so it does not
    itself hit the unrelated, pre-existing sync-render-inside-a-running-
    loop hazard (spec §7 R4).
    """
    import notify.notify as nn

    provider = _DummyProvider()
    assert provider._tpl is nn.TemplateEnv

    d = tmp_path / "templates"
    d.mkdir()
    (d / "hello.html").write_text("Hello {{ name }}!", encoding="utf-8")
    provider._tpl = TemplateParser(directory=d, config={"enable_async": False})

    template = provider._tpl.get_template("hello.html")
    assert template.render(name="Ada") == "Hello Ada!"
