"""Runtime patch for msgraph-core's ``HostOs`` telemetry header.

The Microsoft Graph SDK telemetry middleware
(``msgraph_core.middleware.telemetry.GraphTelemetryHandler``) builds the
``HostOs`` request header from ``platform.system()`` + ``platform.version()``
without sanitising it::

    system = platform.system()      # 'Linux'
    version = platform.version()    # '#107~22.04.1-Ubuntu SMP ... UTC '  (trailing space)
    host_os = f'{system} {version}'
    request.headers.update({'HostOs': host_os})

On some Linux kernels (e.g. Ubuntu HWE) ``platform.version()`` ends with a
trailing space, producing an HTTP header value that ``h11`` (httpx's protocol
backend, used by the Graph SDK) rejects with ``Illegal header value``. The
Teams provider, which dispatches messages through the Graph API, then fails.

This module monkeypatches the handler so the value is stripped of illegal
surrounding whitespace. It is idempotent and safe to call repeatedly.

The bug is still present in msgraph-core 1.4.0, so a version bump does not fix
it. Remove this patch once msgraph-core sanitises the header upstream.
"""
import logging
import platform
from typing import Any

_PATCHED: bool = False


def patch_graph_host_os_header() -> bool:
    """Sanitise the ``HostOs`` telemetry header set by msgraph-core.

    Replaces ``GraphTelemetryHandler._add_host_os_header`` with a variant that
    strips illegal surrounding whitespace from the OS version string before it
    becomes an HTTP header value.

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
    logging.getLogger(__name__).debug(
        "Patched msgraph-core GraphTelemetryHandler: sanitised HostOs header."
    )
    return True
