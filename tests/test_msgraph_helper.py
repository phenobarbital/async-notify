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


# --- AsyncGraphTransport pipeline patch (kiota-http >= 1.14) ---------------

_KEY = "kiota_request_options"


class _FakeRequest:
    """httpx.Request stand-in: kiota-http 1.14 carries options in ``extensions``."""

    def __init__(self, extensions=None):
        self.headers = {}
        self.extensions = extensions if extensions is not None else {}


class _FakePipeline:
    _first_middleware = None

    def __init__(self):
        self.sent = []

    async def send(self, request):
        self.sent.append(request)
        return "pipeline-response"


class _FakeTransport:
    def __init__(self):
        self.sent = []

    async def handle_async_request(self, request):
        self.sent.append(request)
        return "transport-response"


def _patched_transport_class(monkeypatch):
    """Apply the transport patch as if kiota-http 1.14 were installed; undo it on teardown."""
    from kiota_http.middleware import middleware as kiota_middleware
    from msgraph_core.middleware.async_graph_transport import AsyncGraphTransport

    monkeypatch.setattr(kiota_middleware, "REQUEST_OPTIONS_KEY", _KEY, raising=False)
    monkeypatch.setattr(AsyncGraphTransport, "handle_async_request", AsyncGraphTransport.handle_async_request)
    monkeypatch.setattr(_msgraph, "_TRANSPORT_PATCHED", False)
    assert _msgraph.patch_graph_transport_request_options() is True
    return AsyncGraphTransport


async def test_transport_patch_runs_pipeline_with_options_from_extensions(monkeypatch):
    transport_cls = _patched_transport_class(monkeypatch)
    pipeline, inner = _FakePipeline(), _FakeTransport()
    options = {"UrlReplaceHandlerOption": object()}
    request = _FakeRequest({_KEY: options})

    response = await transport_cls(inner, pipeline).handle_async_request(request)

    assert response == "pipeline-response"
    assert pipeline.sent == [request] and inner.sent == []
    assert request.options is options
    assert request.context is not None


async def test_transport_patch_defaults_options_when_extensions_empty(monkeypatch):
    transport_cls = _patched_transport_class(monkeypatch)
    pipeline = _FakePipeline()
    request = _FakeRequest()

    await transport_cls(_FakeTransport(), pipeline).handle_async_request(request)

    assert request.options == {}
    assert pipeline.sent == [request]


async def test_transport_patch_keeps_existing_request_options(monkeypatch):
    transport_cls = _patched_transport_class(monkeypatch)
    request = _FakeRequest({_KEY: {"from": "extensions"}})
    request.options = {"from": "attribute"}

    await transport_cls(_FakeTransport(), _FakePipeline()).handle_async_request(request)

    assert request.options == {"from": "attribute"}


async def test_transport_patch_without_pipeline_uses_inner_transport(monkeypatch):
    transport_cls = _patched_transport_class(monkeypatch)
    inner = _FakeTransport()
    request = _FakeRequest()

    response = await transport_cls(inner, None).handle_async_request(request)

    assert response == "transport-response"
    assert inner.sent == [request]


def test_transport_patch_is_idempotent(monkeypatch):
    _patched_transport_class(monkeypatch)
    assert _msgraph.patch_graph_transport_request_options() is True


def test_transport_patch_returns_false_on_old_kiota_http(monkeypatch):
    from kiota_http.middleware import middleware as kiota_middleware

    monkeypatch.delattr(kiota_middleware, "REQUEST_OPTIONS_KEY", raising=False)
    monkeypatch.setattr(_msgraph, "_TRANSPORT_PATCHED", False)
    assert _msgraph.patch_graph_transport_request_options() is False


def test_apply_msgraph_patches_combines_results(monkeypatch):
    monkeypatch.setattr(_msgraph, "patch_graph_host_os_header", lambda: True)
    monkeypatch.setattr(_msgraph, "patch_graph_transport_request_options", lambda: False)
    assert _msgraph.apply_msgraph_patches() is False
    monkeypatch.setattr(_msgraph, "patch_graph_transport_request_options", lambda: True)
    assert _msgraph.apply_msgraph_patches() is True
