"""Headless device-code login for the Office365 Graph delegated flow (FEAT-004, M8).

Usage:
    python -m notify.providers.office365.login --username me@contoso.com \\
        [--tenant-id <tenant>] [--client-id <client>] [--token-store file|redis]

Seeds the configured token store with a delegated MSAL cache via MSAL's
device-code flow — no browser redirect, no `input()` prompt, safe to run
on a headless server. All CLI output goes to `sys.stderr`; no secret,
token, or cache content is ever printed.
"""

import argparse
import asyncio
import sys
from typing import Optional

from notify.conf import O365_CLIENT_ID, O365_TENANT_ID
from notify.exceptions import NotifyAuthError
from notify.providers.office365.credential import AuthFlow, MsalAsyncCredential
from notify.providers.office365.token_store import TokenStore, build_token_store


async def device_code_login(*, username: str, tenant_id: str, client_id: str, token_store: TokenStore) -> None:
    """Run the delegated device-code flow and persist the resulting cache.

    Args:
        username: The account to sign in as (matched case-insensitively by
            `MsalAsyncCredential` against the cached account's username on
            later `get_token` calls).
        tenant_id: The Entra ID tenant to authenticate against.
        client_id: The app registration's client id (must allow public
            client flows / device code).
        token_store: Where the resulting serialized MSAL cache is persisted.

    Raises:
        NotifyAuthError: If the device flow cannot start or complete
            (including a timeout while waiting for the user to sign in).
    """
    credential = MsalAsyncCredential(
        flow=AuthFlow.DELEGATED,
        tenant_id=tenant_id,
        client_id=client_id,
        username=username,
        token_store=token_store,
    )
    flow = await credential.initiate_device_flow()
    sys.stderr.write(f"{flow.get('message', 'Go sign in with the device code shown above.')}\n")
    try:
        await credential.complete_device_flow(flow)
    finally:
        await credential.close()


def main(argv: Optional[list[str]] = None) -> int:
    """Parse arguments and run the headless device-code login.

    Args:
        argv: Argument list; defaults to `sys.argv[1:]` when `None`.

    Returns:
        int: `0` on success, `1` for a `NotifyAuthError` (including a
        device-code timeout), `2` for invalid arguments.
    """
    parser = argparse.ArgumentParser(
        prog="python -m notify.providers.office365.login",
        description="Headless one-time delegated sign-in for the Office365 Graph provider.",
    )
    parser.add_argument("--username", required=True, help="The account to sign in as.")
    parser.add_argument(
        "--tenant-id", default=O365_TENANT_ID, help="Entra ID tenant (default: O365_TENANT_ID setting)."
    )
    parser.add_argument(
        "--client-id", default=O365_CLIENT_ID, help="App registration client id (default: O365_CLIENT_ID setting)."
    )
    parser.add_argument(
        "--token-store",
        choices=("memory", "file", "redis"),
        default="file",
        help="Where to persist the delegated token cache ('memory' is refused — it would lose the token).",
    )
    args = parser.parse_args(argv)

    if args.token_store == "memory":
        sys.stderr.write(
            "Error: --token-store memory would lose the token as soon as this process exits; "
            "use --token-store file or --token-store redis instead.\n"
        )
        return 2
    if not args.tenant_id:
        sys.stderr.write("Error: --tenant-id is required (or set the O365_TENANT_ID setting).\n")
        return 2
    if not args.client_id:
        sys.stderr.write("Error: --client-id is required (or set the O365_CLIENT_ID setting).\n")
        return 2

    token_store = build_token_store(args.token_store)

    try:
        asyncio.run(
            device_code_login(
                username=args.username,
                tenant_id=args.tenant_id,
                client_id=args.client_id,
                token_store=token_store,
            )
        )
    except NotifyAuthError as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return 1

    sys.stderr.write(f"O365 delegated sign-in succeeded for {args.username}.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
