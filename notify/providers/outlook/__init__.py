"""
Outlook (Microsoft Graph).

`Outlook` is a backward-compatible alias of the Graph-based `Office365`
provider (see `notify.providers.office365`): same constructor, same auth
flows, same send() behavior, plus the legacy `add_attachment(filename)`
queueing API.
"""

from .outlook import Outlook

__all__ = ["Outlook"]
