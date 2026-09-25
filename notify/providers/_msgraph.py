"""Shared Microsoft Graph helpers used by every Graph-based provider.

Holds the runtime patches for msgraph-core (the ``HostOs`` telemetry header,
moved here verbatim from ``notify.providers.teams._msgraph_patch``, and the
``AsyncGraphTransport`` middleware pipeline under kiota-http >= 1.14) so both
``teams`` and ``office365`` share one implementation, plus the default Graph
scope constant used by client-credentials-style auth flows.

Graph-based providers call :func:`apply_msgraph_patches` at import time.
"""

import logging
import platform
from typing import Any

#: Default `.default` scope for Microsoft Graph app-only/OBO/ROPC token
#: requests (the delegated flow uses its own narrower scopes; see
#: notify/providers/office365/credential.py).
GRAPH_DEFAULT_SCOPE: str = "https://graph.microsoft.com/.default"

_PATCHED: bool = False


def patch_graph_host_os_header() -> bool:
    """Sanitise the ``HostOs`` telemetry header set by msgraph-core.

    The Microsoft Graph SDK telemetry middleware
    (``msgraph_core.middleware.telemetry.GraphTelemetryHandler``) builds the
    ``HostOs`` request header from ``platform.system()`` + ``platform.version()``
    without sanitising it. On some Linux kernels (e.g. Ubuntu HWE)
    ``platform.version()`` ends with a trailing space, producing an HTTP
    header value that ``h11`` (httpx's protocol backend, used by the Graph
    SDK) rejects with ``Illegal header value``.

    This replaces ``GraphTelemetryHandler._add_host_os_header`` with a
    variant that strips illegal surrounding whitespace from the OS version
    string before it becomes an HTTP header value. It is idempotent and safe
    to call repeatedly.

    The bug is still present in msgraph-core 1.4.0, so a version bump does
    not fix it. Remove this patch once msgraph-core sanitises the header
    upstream.

    Returns:
        bool: ``True`` if the patch is in place (applied now or previously),
            ``False`` if the target could not be located (msgraph-core absent
            or its internals changed).
    """
    global _PATCHED
    if _PATCHED:
        return True
    try:
        from msgraph_core.middleware.telemetry import GraphTelemetryHandler
    except Exception:  # pragma: no cover - msgraph-core optional/absent
        return False

    def _add_host_os_header(self, request: Any) -> None:
        host_os = f"{platform.system()} {platform.version()}".strip()
        request.headers.update({"HostOs": host_os})

    GraphTelemetryHandler._add_host_os_header = _add_host_os_header
    _PATCHED = True
    logging.getLogger(__name__).debug("Patched msgraph-core GraphTelemetryHandler: sanitised HostOs header.")
    return True


_TRANSPORT_PATCHED: bool = False


def patch_graph_transport_request_options() -> bool:
    """Run the msgraph-core middleware pipeline with kiota-http >= 1.14.

    ``msgraph_core.middleware.async_graph_transport.AsyncGraphTransport`` only
    runs the middleware pipeline when the request has an ``options``
    attribute::

        if self.pipeline and hasattr(request, 'options'):
            ...
            response = await self.pipeline.send(request)

    microsoft-kiota-http 1.14 stopped setting ``request.options`` and passes
    the request options through ``request.extensions`` instead. The check
    never passes, so msgraph-core skips every middleware (UrlReplace, Retry,
    Redirect, Telemetry). Without ``UrlReplaceHandler`` the SDK sends
    ``/users/me-token-to-replace`` as is instead of ``/me``, so
    ``graph.me.get()`` fails with a 404 (Teams with ``as_user=True``), and
    429/503 responses are never retried.

    This replaces ``AsyncGraphTransport.handle_async_request`` with a variant
    that fills ``request.options`` from ``request.extensions`` when it is
    missing, then runs the pipeline. It is idempotent and safe to call
    repeatedly. On kiota-http releases without ``REQUEST_OPTIONS_KEY`` (< 1.14,
    which still set ``request.options``) nothing is patched. Remove it once
    msgraph-core supports the kiota-http 1.14 request options.

    Returns:
        bool: ``True`` if the patch is in place (applied now or previously),
            ``False`` if the target could not be located (msgraph-core or
            kiota-http absent, kiota-http < 1.14, or their internals changed).
    """
    global _TRANSPORT_PATCHED
    if _TRANSPORT_PATCHED:
        return True
    try:
        from kiota_http.middleware.middleware import REQUEST_OPTIONS_KEY
        from msgraph_core.middleware.async_graph_transport import AsyncGraphTransport
    except ImportError:  # msgraph-core/kiota-http absent, or kiota-http < 1.14
        return False

    async def handle_async_request(self, request: Any) -> Any:
        if self.pipeline:
            if not hasattr(request, "options"):
                request.options = request.extensions.get(REQUEST_OPTIONS_KEY) or {}
            self.set_request_context_and_feature_usage(request)
            return await self.pipeline.send(request)
        return await self.transport.handle_async_request(request)

    AsyncGraphTransport.handle_async_request = handle_async_request
    _TRANSPORT_PATCHED = True
    logging.getLogger(__name__).debug("Patched msgraph-core AsyncGraphTransport: middleware pipeline restored.")
    return True


def apply_msgraph_patches() -> bool:
    """Apply every msgraph-core runtime patch in this module.

    Returns:
        bool: ``True`` if all patches are in place, ``False`` otherwise.
    """
    host_os = patch_graph_host_os_header()
    transport = patch_graph_transport_request_options()
    return host_os and transport
