"""
Zoom Phone Number Lookup.

Lists all Zoom Phone users and their assigned phone numbers.
Uses Zoom S2S OAuth credentials from the environment.

Usage::

    ENV=production python examples/zoom_phone_lookup.py

Optionally filter by email, name, or phone::

    ENV=production python examples/zoom_phone_lookup.py --search "john"
"""
import argparse
import asyncio
import sys

import aiohttp
from navconfig import config


ZOOM_AUTH_URL = "https://zoom.us/oauth/token"
ZOOM_API_BASE = "https://api.zoom.us/v2"


async def get_token(
    session: aiohttp.ClientSession,
    account_id: str,
    client_id: str,
    client_secret: str,
) -> str:
    """Fetch an OAuth access token via Server-to-Server credentials grant.

    Args:
        session: Active aiohttp session.
        account_id: Zoom account ID.
        client_id: OAuth client ID.
        client_secret: OAuth client secret.

    Returns:
        Access token string.

    Raises:
        RuntimeError: If token request fails.
    """
    auth = aiohttp.BasicAuth(client_id, client_secret)
    data = {
        "grant_type": "account_credentials",
        "account_id": account_id,
    }
    async with session.post(ZOOM_AUTH_URL, auth=auth, data=data) as resp:
        if resp.status != 200:
            error = await resp.text()
            raise RuntimeError(
                f"OAuth token request failed ({resp.status}): {error}"
            )
        result = await resp.json()
        token = result.get("access_token")
        if not token:
            raise RuntimeError("No access_token in OAuth response")
        return token


async def list_phone_users(
    session: aiohttp.ClientSession,
    token: str,
    search: str | None = None,
) -> None:
    """Fetch and display all Zoom Phone users and their numbers.

    Args:
        session: Active aiohttp session.
        token: Valid OAuth access token.
        search: Optional case-insensitive filter for name, email, or phone.
    """
    headers = {"Authorization": f"Bearer {token}"}
    next_page_token = ""
    page = 0
    total_found = 0

    while True:
        page += 1
        params: dict = {"page_size": 100}
        if next_page_token:
            params["next_page_token"] = next_page_token

        url = f"{ZOOM_API_BASE}/phone/users"
        async with session.get(url, headers=headers, params=params) as resp:
            if resp.status != 200:
                body = await resp.text()
                print(f"[✗] API error ({resp.status}): {body}", file=sys.stderr)
                return
            data = await resp.json()

        users = data.get("users", [])
        print(f"\n--- Page {page} ({len(users)} users) ---")

        for user in users:
            name = user.get("name", "N/A")
            email = user.get("email", "N/A")
            extension = user.get("extension_number", "N/A")
            phone_numbers = user.get("phone_numbers", [])
            status = user.get("status", "N/A")

            # Apply search filter
            if search:
                needle = search.lower()
                haystack = f"{name} {email}".lower()
                phone_str = " ".join(
                    pn.get("number", "") for pn in phone_numbers
                )
                haystack += f" {phone_str}"
                if needle not in haystack:
                    continue

            total_found += 1
            numbers_str = ", ".join(
                pn.get("number", "?") for pn in phone_numbers
            ) or "(no numbers assigned)"

            print(
                f"  {name:<30} | {email:<40} | "
                f"ext: {extension:<6} | status: {status:<10} | "
                f"phones: {numbers_str}"
            )

        next_page_token = data.get("next_page_token", "")
        if not next_page_token:
            break

    print(f"\n[✓] Total users found: {total_found}")


async def run(search: str | None = None) -> None:
    """Entry point: authenticate and list phone users.

    Args:
        search: Optional filter string.
    """
    # Try the general ZOOM credentials first, fall back to ZOOM_SMS_*
    account_id = config.get("ZOOM_ACCOUNT_ID") or config.get("ZOOM_SMS_ACCOUNT_ID")
    client_id = config.get("ZOOM_CLIENT_ID") or config.get("ZOOM_SMS_CLIENT_ID")
    client_secret = config.get("ZOOM_CLIENT_SECRET") or config.get("ZOOM_SMS_CLIENT_SECRET")

    if not all([account_id, client_id, client_secret]):
        print(
            "[✗] Missing Zoom credentials. Set ZOOM_ACCOUNT_ID / ZOOM_CLIENT_ID "
            "/ ZOOM_CLIENT_SECRET (or ZOOM_SMS_*) in the environment.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"[*] Account ID : {account_id}")
    print(f"[*] Client ID  : {client_id}")
    print(f"[*] Authenticating ...")

    async with aiohttp.ClientSession() as session:
        token = await get_token(session, account_id, client_id, client_secret)
        print("[✓] Token acquired.")
        await list_phone_users(session, token, search=search)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="List Zoom Phone users and their assigned phone numbers.",
    )
    parser.add_argument(
        "--search",
        default=None,
        help="Filter users by name, email, or phone number (case-insensitive).",
    )
    args = parser.parse_args()

    try:
        asyncio.run(run(search=args.search))
    except KeyboardInterrupt:
        print("\n[!] Cancelled.")
        sys.exit(130)
    except Exception as exc:
        print(f"[✗] Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
