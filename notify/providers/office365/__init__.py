"""
Office 365 Email (Microsoft Graph).

Sends email through Microsoft Graph (`msgraph-sdk`) with four auth flows
(client credentials, on-behalf-of, delegated, and the deprecated password
flow), send-as routing, pluggable encrypted token stores, and attachments
(including inline CID images and >3 MB upload sessions). See
`notify.providers.office365.office365.Office365` and
`notify.providers.outlook` (the same Graph core, kept as a compatible alias).
"""

from .office365 import Office365

__all__ = ("Office365",)
