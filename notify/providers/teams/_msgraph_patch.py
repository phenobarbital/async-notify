"""Backward-compatible re-export of the shared Microsoft Graph HostOs patch.

The implementation moved to ``notify.providers._msgraph`` (FEAT-004, M1) so
every Graph-based provider (``teams``, ``office365``) shares one copy. This
module is kept as a compatibility shim so the old import path,
``from notify.providers.teams._msgraph_patch import patch_graph_host_os_header``,
keeps working unchanged.
"""
from notify.providers._msgraph import patch_graph_host_os_header  # re-export, keeps old import path

__all__ = ("patch_graph_host_os_header",)
