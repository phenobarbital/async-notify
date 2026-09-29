"""Outlook Client — Microsoft Graph core alias (FEAT-004, M7).

`Outlook` is a thin, silent alias of the Graph-based `Office365` provider:
same constructor, same four auth flows, same `send()` behavior. It exists
only so `Notify("outlook", ...)` keeps working for existing callers. The
previous implementation depended on `Office365-REST-Python-Client`
(`office365.graph_client.GraphClient`), which the project owner confirmed
is broken; that dependency, and the direct `acquire_token()` /
`acquire_token_by_username()` methods that used it, are removed entirely.

The legacy `add_attachment(filename)` queueing API is kept: a queued file
is merged into the next `send()`'s attachments and the queue is cleared
afterwards (even if that send fails).
"""

from pathlib import Path
from typing import Any, Union

from notify.models import Actor, MailSendResult
from notify.providers.office365.office365 import Office365


class Outlook(Office365):
    """Alias of the Graph-based `Office365` provider kept for backward compatibility."""

    provider = "outlook"

    def __init__(self, *args, **kwargs) -> None:
        self._pending_attachments: list[Path] = []
        super().__init__(*args, **kwargs)

    async def add_attachment(self, filename: Union[str, Path]) -> None:
        """Queue a file to attach to the next `send()`.

        Args:
            filename: Path to the file to attach.

        Raises:
            FileNotFoundError: If `filename` does not exist.
        """
        path = Path(filename) if isinstance(filename, str) else filename
        if not path.exists():
            raise FileNotFoundError(f"Attachment Error: {path} does not exist.")
        self._pending_attachments.append(path)

    async def _send_(self, to: list[Actor], message: str, subject: str = None, **kwargs: Any) -> MailSendResult:
        """Merge queued attachments into `kwargs['attachments']`, delegate to
        `Office365._send_`, then clear the queue — even if the send fails.
        """
        if self._pending_attachments:
            attachments = list(kwargs.get("attachments") or [])
            attachments.extend(self._pending_attachments)
            kwargs["attachments"] = attachments
        try:
            return await super()._send_(to, message, subject=subject, **kwargs)
        finally:
            self._pending_attachments = []
