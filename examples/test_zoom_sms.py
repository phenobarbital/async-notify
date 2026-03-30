"""
Test Zoom SMS Provider.

Sends an SMS via the Zoom Phone API using the ``Zoom`` provider.

Usage::

    ENV=production uv run python examples/test_zoom_sms.py \
        --from-number "+18001234567" \
        --to-number "+15551234567" \
        --to-name "John Doe" \
        --message "Hello from FlowTask!"

The script reads ``ZOOM_SMS_ACCOUNT_ID``, ``ZOOM_SMS_CLIENT_ID``, and
``ZOOM_SMS_CLIENT_SECRET`` from the environment (via navconfig).

``--from-number`` overrides ``ZOOM_SMS_DEFAULT_FROM`` for this run.
"""
import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to sys.path to ensure we load the local 'notify' package
sys.path.insert(0, str(Path(__file__).parent.parent))

from notify.providers.zoom import Zoom
from notify.models import Actor


async def send_sms(
    from_number: str,
    to_number: str,
    to_name: str,
    message: str,
    user_id: str = None,
) -> None:
    """Authenticate with Zoom and send a single SMS.

    Args:
        from_number: Sender phone number (E.164).
        to_number: Recipient phone number (E.164).
        to_name: Recipient display name.
        message: SMS body text (max 500 chars).
        user_id: User ID of the sender.
    """
    recipient = Actor(
        name=to_name,
        account={
            "number": to_number, 
            "provider": "zoom"
        },
    )

    zoom = Zoom(from_number=from_number, user_id=user_id)

    print(f"[*] Connecting to Zoom (account_id={zoom.account_id!r}) ...")
    async with zoom as provider:
        print(
            f"[*] Sending SMS from {from_number} → {to_number} "
            f"({to_name})"
        )
        results = await provider.send(
            recipient=recipient,
            message=message,
        )
        if results:
            for result in results:
                print(f"[✓] Success: {result}")
        else:
            print("[!] No results returned from provider.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send a test SMS via the Zoom Phone API.",
    )
    parser.add_argument(
        "--from-number",
        required=True,
        help="Sender phone number in E.164 format (e.g. +18001234567).",
    )
    parser.add_argument(
        "--to-number",
        required=True,
        help="Recipient phone number in E.164 format (e.g. +15551234567).",
    )
    parser.add_argument(
        "--to-name",
        default="Test Recipient",
        help="Display name of the recipient (default: 'Test Recipient').",
    )
    parser.add_argument(
        "--message",
        default="Hello from async-notify Zoom SMS test!",
        help="SMS message body (max 500 characters).",
    )
    parser.add_argument(
        "--user-id",
        required=False,
        default=None,
        help="Sender User ID for Server-to-Server SMS requests.",
    )
    args = parser.parse_args()

    if len(args.message) > 500:
        print("[!] Warning: message exceeds 500 chars; Zoom will truncate it.")

    try:
        asyncio.run(
            send_sms(
                from_number=args.from_number,
                to_number=args.to_number,
                to_name=args.to_name,
                message=args.message,
                user_id=args.user_id,
            )
        )
    except KeyboardInterrupt:
        print("\n[!] Cancelled.")
        sys.exit(130)
    except Exception as exc:
        print(f"[✗] Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
