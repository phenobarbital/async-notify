"""Provider resolution and optional-dependency diagnostics (FEAT-005, M1).

Locks spec §5 goals G1 (actionable missing-dependency diagnostics) and G2
(correct provider resolution via ``__all__``).
"""

import importlib.abc
import logging
import sys
from unittest import mock

import pytest

import notify.notify as notify_module
from notify import Notify
from notify.exceptions import ProviderDependencyError, ProviderError
from notify.notify import PROVIDERS, LoadProvider, _known_providers

#: Aliases whose provider module is broken for reasons unrelated to FEAT-005
#: (a raw, non-ModuleNotFoundError ``ImportError`` that must propagate as-is).
KNOWN_BROKEN_ALIASES = {
    "onesignal": "imports ProviderIMBase, which notify.providers.base does not define",
}


class _AbsentFinder(importlib.abc.MetaPathFinder):
    """Make a top-level module look genuinely absent.

    Raises ``ModuleNotFoundError`` with ``.name`` set from :meth:`find_spec`,
    exactly what the import machinery raises for a package that is not
    installed — the discriminator ``LoadProvider`` keys on.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    def find_spec(self, fullname, path, target=None):
        """Refuse ``self.name`` and its submodules as a missing module."""
        if fullname == self.name or fullname.startswith(f"{self.name}."):
            raise ModuleNotFoundError(f"No module named {fullname!r}", name=fullname)
        return None


class _BrokenFinder(importlib.abc.MetaPathFinder):
    """Make a module raise a NON-ModuleNotFoundError ImportError."""

    def __init__(self, name: str) -> None:
        self.name = name

    def find_spec(self, fullname, path, target=None):
        """Raise a plain ``ImportError`` for ``self.name`` and its submodules."""
        if fullname == self.name or fullname.startswith(f"{self.name}."):
            raise ImportError(f"exploding import of {fullname!r}")
        return None


def _evict(monkeypatch: pytest.MonkeyPatch, sdk: str, alias: str) -> None:
    """Evict provider/SDK modules and the PROVIDERS memo entry (restored on teardown)."""
    monkeypatch.delitem(PROVIDERS, alias, raising=False)
    prefixes = (f"notify.providers.{alias}", sdk)
    for key in list(sys.modules):
        if any(key == prefix or key.startswith(f"{prefix}.") for prefix in prefixes):
            monkeypatch.delitem(sys.modules, key, raising=False)


@pytest.fixture
def blocked_module(monkeypatch):
    """Make a top-level module unimportable for the duration of a test.

    Yields a callable ``block(sdk, alias)`` that evicts the provider package,
    the SDK's own modules and the ``PROVIDERS`` memo entry, then makes the SDK
    raise a genuine ``ModuleNotFoundError``. Everything is restored on teardown
    by ``monkeypatch``.
    """

    def block(sdk: str, alias: str) -> None:
        _evict(monkeypatch, sdk, alias)
        monkeypatch.setattr(sys, "meta_path", [_AbsentFinder(sdk), *sys.meta_path])
        with pytest.raises(ModuleNotFoundError) as excinfo:
            importlib_import(sdk)
        assert excinfo.value.name == sdk

    return block


def importlib_import(name: str):
    """Import ``name`` (helper so the fixture sanity check reads clearly)."""
    import importlib

    return importlib.import_module(name)


def test_dependency_error_is_a_provider_error():
    """AC — existing ``except ProviderError`` handlers keep working."""
    assert issubclass(ProviderDependencyError, ProviderError)


async def test_smtp_alias_resolves():
    """AC-G2 — fails on ``dev`` today: the package exports ``SMTP``, not ``Smtp``."""
    from notify.providers.smtp import SMTP

    assert isinstance(Notify("smtp"), SMTP)


def test_all_aliases_resolve_to_a_class():
    """AC-G2 — every package resolves via ``__all__``, without instantiating."""
    aliases = _known_providers()
    assert "smtp" in aliases
    for alias in aliases:
        if alias in KNOWN_BROKEN_ALIASES:
            continue
        try:
            cls = LoadProvider(alias)
        except ProviderDependencyError:
            if alias == "smtp":
                raise
            continue  # SDK genuinely not installed in this environment
        assert isinstance(cls, type), alias


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
    message = str(excinfo.value)
    assert "dummy" in message
    assert "smtp" in message


def test_notify_factory_preserves_error_subclass(blocked_module):
    """AC-G1 — ``Notify.__new__`` and ``Notify.provider`` must not flatten it."""
    blocked_module("aiogram", "telegram")
    with pytest.raises(ProviderDependencyError):
        Notify("telegram")
    with pytest.raises(ProviderDependencyError):
        Notify.provider("telegram")


def test_internal_import_error_is_not_masked(monkeypatch):
    """AC-G1 — a non-ModuleNotFoundError ImportError propagates unchanged."""
    _evict(monkeypatch, "aiogram", "telegram")
    monkeypatch.setattr(sys, "meta_path", [_BrokenFinder("aiogram"), *sys.meta_path])
    with pytest.raises(ImportError) as excinfo:
        LoadProvider("telegram")
    assert not isinstance(excinfo.value, ModuleNotFoundError)
    assert not isinstance(excinfo.value, ProviderDependencyError)
    assert "exploding import" in str(excinfo.value)
    assert PROVIDERS.get("telegram") is None


def test_failed_load_is_not_cached(blocked_module):
    """A failed load leaves no ``PROVIDERS`` entry behind."""
    blocked_module("aiogram", "telegram")
    with pytest.raises(ProviderDependencyError):
        Notify("telegram")
    assert "telegram" not in PROVIDERS


def test_neither_path_logs_at_critical(blocked_module, caplog, monkeypatch):
    """AC-G1 — "Neither path logs at CRITICAL"."""
    blocked_module("aiogram", "telegram")
    fake_logger = mock.MagicMock()
    monkeypatch.setattr(notify_module, "logger", fake_logger)
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ProviderError):
            Notify("does_not_exist")
        with pytest.raises(ProviderDependencyError):
            Notify("telegram")
    assert not fake_logger.critical.called
    assert all(record.levelno < logging.CRITICAL for record in caplog.records)
