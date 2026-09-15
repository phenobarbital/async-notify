"""Offline tests for the shared Microsoft Graph telemetry helper (FEAT-004, M1)."""
from notify.providers import _msgraph
from notify.providers.teams import _msgraph_patch


def test_graph_default_scope_constant():
    assert _msgraph.GRAPH_DEFAULT_SCOPE == "https://graph.microsoft.com/.default"


def test_shim_reexports_same_callable():
    assert _msgraph_patch.patch_graph_host_os_header is _msgraph.patch_graph_host_os_header


def test_patch_is_idempotent(monkeypatch):
    monkeypatch.setattr(_msgraph, "_PATCHED", False)
    first = _msgraph.patch_graph_host_os_header()
    second = _msgraph.patch_graph_host_os_header()
    assert first == second is True


def test_patch_returns_false_when_msgraph_core_absent(monkeypatch):
    import builtins

    monkeypatch.setattr(_msgraph, "_PATCHED", False)

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "msgraph_core.middleware.telemetry":
            raise ImportError("msgraph-core not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    assert _msgraph.patch_graph_host_os_header() is False


def test_patched_handler_strips_trailing_whitespace(monkeypatch):
    monkeypatch.setattr(_msgraph, "_PATCHED", False)
    from msgraph_core.middleware.telemetry import GraphTelemetryHandler

    assert _msgraph.patch_graph_host_os_header() is True

    class _FakeRequest:
        def __init__(self):
            self.headers = {}

    monkeypatch.setattr(_msgraph.platform, "system", lambda: "Linux")
    monkeypatch.setattr(_msgraph.platform, "version", lambda: "#107~22.04.1-Ubuntu SMP  ")

    request = _FakeRequest()
    GraphTelemetryHandler._add_host_os_header(None, request)
    assert request.headers["HostOs"] == "Linux #107~22.04.1-Ubuntu SMP"
