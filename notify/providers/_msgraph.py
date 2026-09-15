"""Shared Microsoft Graph helpers used by every Graph-based provider.

Currently holds the runtime patch for msgraph-core's ``HostOs`` telemetry
header (moved here, verbatim, from ``notify.providers.teams._msgraph_patch``
so both ``teams`` and ``office365`` can share one implementation), plus the
default Graph scope constant used by client-credentials-style auth flows.
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
