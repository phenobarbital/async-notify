"""
Zoom SMS Provider.

Provider for sending SMS messages via the Zoom Phone API
using Server-to-Server OAuth authentication.

Endpoint: ``POST /phone/sms/messages``

Required Zoom Scopes (any one):
    ``phone_sms:write``, ``phone_sms:write:admin``,
    ``phone:write``, ``phone:write:admin``

Usage::

    from notify import Notify

    zoom = Notify("zoom", from_number="+17865391724")
    async with zoom as conn:
        await conn.send(
            recipient=Actor(
                name="Juan",
                account={"phone": "+15551234567"}
            ),
            message="Hello from FlowTask!",
        )
"""
import time as _time
from typing import Any, Union, Optional

import aiohttp
from navconfig.logging import logging

from notify.providers.base import ProviderMessaging, ProviderType
from notify.models import Actor
from notify.exceptions import ProviderError
from notify.conf import (
    ZOOM_ACCOUNT_ID,
    ZOOM_CLIENT_ID,
    ZOOM_CLIENT_SECRET,
    ZOOM_SMS_DEFAULT_FROM,
)


# Zoom API constants
ZOOM_AUTH_URL = "https://zoom.us/oauth/token"
ZOOM_API_BASE = "https://api.zoom.us/v2"


class Zoom(ProviderMessaging):
    """Zoom Phone SMS Provider.

    Sends SMS messages through the Zoom Phone API.
    Authenticates via Server-to-Server OAuth (account credentials grant).

    Args:
        account_id: Zoom account ID. Defaults to ``ZOOM_ACCOUNT_ID``.
        client_id: OAuth client ID. Defaults to ``ZOOM_CLIENT_ID``.
        client_secret: OAuth client secret. Defaults to ``ZOOM_CLIENT_SECRET``.
        from_number: Sender phone number in E.164 format.
            Must be an SMS-capable Zoom Phone number.
            Defaults to ``ZOOM_SMS_DEFAULT_FROM``.

    Attributes:
        provider: Provider name (``"zoom"``).
        provider_type: Set to ``ProviderType.SMS``.
    """

    provider = "zoom"
    provider_type = ProviderType.SMS
    level = ""
    blocking: str = "asyncio"

    def __init__(
        self,
        account_id: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        from_number: Optional[str] = None,
        **kwargs,
    ):
        self._msg = None
        self.session: Optional[aiohttp.ClientSession] = None
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0
        super(Zoom, self).__init__(**kwargs)
        self.account_id = account_id or ZOOM_ACCOUNT_ID
        self.client_id = client_id or ZOOM_CLIENT_ID
        self.client_secret = client_secret or ZOOM_CLIENT_SECRET
        self.from_number = from_number or ZOOM_SMS_DEFAULT_FROM

    async def connect(self, *args, **kwargs):
        """Establish connection: create HTTP session and fetch OAuth token.

        Raises:
            RuntimeError: If credentials are missing or token fetch fails.
        """
        if not all([self.account_id, self.client_id, self.client_secret]):
            raise RuntimeError(
                f"To send SMS via {self.__class__.__name__} you need to "
                "configure ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID & "
                "ZOOM_CLIENT_SECRET in environment variables or pass them "
                "as parameters."
            )
        if not self.from_number:
            raise RuntimeError(
                "Zoom SMS requires a sender phone number. "
                "Set ZOOM_SMS_DEFAULT_FROM or pass from_number."
            )
        self.session = aiohttp.ClientSession()
        await self._refresh_token()

    async def close(self):
        """Close the HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    async def _refresh_token(self) -> str:
        """Fetch or refresh the OAuth access token.

        Uses Server-to-Server OAuth (account_credentials grant).
        Tokens are cached with a 60-second safety margin.

        Returns:
            Valid access token string.

        Raises:
            ProviderError: If the token request fails.
        """
        # Return cached token if still valid
        if self._token and _time.time() < self._token_expiry:
            return self._token

        auth = aiohttp.BasicAuth(self.client_id, self.client_secret)
        data = {
            "grant_type": "account_credentials",
            "account_id": self.account_id,
        }
        try:
            async with self.session.post(
                ZOOM_AUTH_URL, auth=auth, data=data
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise ProviderError(
                        f"Zoom OAuth token request failed "
                        f"({resp.status}): {error}"
                    )
                result = await resp.json()
                self._token = result.get("access_token")
                if not self._token:
                    raise ProviderError(
                        "No access_token in Zoom OAuth response"
                    )
                expires_in = int(result.get("expires_in", 3600))
                # 60-second safety margin
                self._token_expiry = _time.time() + expires_in - 60
                return self._token
        except aiohttp.ClientError as exc:
            raise ProviderError(
                f"Zoom OAuth connection error: {exc}"
            ) from exc

    async def _send_(
        self,
        to: Actor,
        message: Union[str, Any],
        subject: str = None,
        **kwargs,
    ) -> Any:
        """Send an SMS message to a single recipient.

        Called by ``ProviderBase.send()`` for each recipient.

        Args:
            to: Recipient ``Actor``. Must have
                ``to.account["phone"]`` with an E.164 number.
            message: SMS text content (max 500 characters).
            subject: Not used for SMS, ignored.

        Returns:
            Dict with ``message_id``, ``session_id``, and
            ``date_time`` from the Zoom API response.

        Raises:
            ProviderError: If the API call fails.
        """
        try:
            msg = await self._render_(to, message, **kwargs)
            phone = to.account.get("phone") or to.account.get("number")
            if not phone:
                raise ProviderError(
                    f"Recipient {to.name} has no 'phone' or 'number' "
                    f"in account: {to.account}"
                )

            # Ensure fresh token
            token = await self._refresh_token()

            payload = {
                "sender": {"phone_number": self.from_number},
                "to_members": [{"phone_number": phone}],
                "message": msg[:500],  # Zoom limit
            }

            # Optional: continue existing session
            session_id = kwargs.get("session_id")
            if session_id:
                payload["session_id"] = session_id

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            url = f"{ZOOM_API_BASE}/phone/sms/messages"

            async with self.session.post(
                url, headers=headers, json=payload
            ) as resp:
                body = await resp.json()
                if resp.status == 201:
                    logging.debug(
                        f"Zoom SMS sent to {phone} — "
                        f"message_id={body.get('message_id')}"
                    )
                    return body
                elif resp.status == 401:
                    # Token expired, refresh and retry once
                    self._token = None
                    token = await self._refresh_token()
                    headers["Authorization"] = f"Bearer {token}"
                    async with self.session.post(
                        url, headers=headers, json=payload
                    ) as retry_resp:
                        retry_body = await retry_resp.json()
                        if retry_resp.status == 201:
                            return retry_body
                        raise ProviderError(
                            f"Zoom SMS failed after token refresh "
                            f"({retry_resp.status}): {retry_body}"
                        )
                else:
                    raise ProviderError(
                        f"Zoom SMS API error ({resp.status}): {body}"
                    )
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                f"Error sending SMS via Zoom: {exc}"
            ) from exc
