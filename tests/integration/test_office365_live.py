"""Live Microsoft Graph integration tests for the Office365 provider (FEAT-004).

Every test here is gated by `@pytest.mark.integration` (registered in
`pytest.ini`) and by a `pytest.mark.skipif` that checks the navconfig
settings its scenario needs against the project's existing Entra ID test
tenant. No credential is manufactured here, and the deprecated
`password` (ROPC) flow is never used to obtain one — per spec §8, the
On-Behalf-Of scenario reads a pre-issued user assertion from navconfig.

Run explicitly with:
    pytest -m integration tests/integration/test_office365_live.py -v
"""

from navconfig import config

from notify import Notify
from notify.conf import O365_CLIENT_ID, O365_CLIENT_SECRET, O365_TENANT_ID
from notify.models import Account, Actor

import pytest

pytestmark = pytest.mark.integration

# Test-tenant-only settings: none of these are provider settings (see M9 /
# notify/conf.py), so they are read directly with no default — this file is
# the only consumer.
O365_TEST_SENDER = config.get("O365_TEST_SENDER")  # shared mailbox to send as
O365_TEST_RECIPIENT = config.get("O365_TEST_RECIPIENT")  # inbox the live tests send to
O365_TEST_DENIED_SENDER = config.get("O365_TEST_DENIED_SENDER")  # mailbox without SendAs rights
O365_TEST_USER_ASSERTION = config.get("O365_TEST_USER_ASSERTION")  # pre-issued Graph-audience user token
O365_TEST_DELEGATED_USERNAME = config.get("O365_TEST_DELEGATED_USERNAME")  # pre-seeded via login.py

_APP_ONLY_SETTINGS = (O365_CLIENT_ID, O365_CLIENT_SECRET, O365_TENANT_ID, O365_TEST_SENDER, O365_TEST_RECIPIENT)
_app_only_configured = all(_APP_ONLY_SETTINGS)

_obo_configured = _app_only_configured and bool(O365_TEST_USER_ASSERTION)
_delegated_configured = bool(O365_TENANT_ID and O365_CLIENT_ID and O365_TEST_DELEGATED_USERNAME)
_denied_configured = _app_only_configured and bool(O365_TEST_DENIED_SENDER)


def _recipient() -> Actor:
    return Actor(name="FEAT-004 Live Test", account=Account(address=O365_TEST_RECIPIENT))


@pytest.mark.skipif(not _app_only_configured, reason="O365 app-only test tenant settings are not configured.")
async def test_live_app_only_send_as_shared_mailbox():
    async with Notify("office365", auth_flow="client_credentials", sender=O365_TEST_SENDER) as mail:
        results = await mail.send(
            recipient=[_recipient()],
            subject="FEAT-004 live test: app-only send-as",
            message="<p>Live integration test - app-only send-as a shared mailbox.</p>",
        )
    assert len(results) == 1
    assert results[0].success is True
    assert results[0].mailbox == O365_TEST_SENDER


@pytest.mark.skipif(not _app_only_configured, reason="O365 app-only test tenant settings are not configured.")
async def test_live_app_only_large_attachment(tmp_path):
    big_file = tmp_path / "large-attachment.bin"
    big_file.write_bytes(b"0" * (5 * 1024 * 1024))  # 5 MB forces the draft_upload strategy

    async with Notify("office365", auth_flow="client_credentials", sender=O365_TEST_SENDER) as mail:
        results = await mail.send(
            recipient=[_recipient()],
            subject="FEAT-004 live test: 5MB attachment via upload session",
            message="<p>Live integration test - large attachment.</p>",
            attachments=[str(big_file)],
        )
    assert len(results) == 1
    assert results[0].success is True
    assert results[0].strategy == "draft_upload"


@pytest.mark.skipif(not _app_only_configured, reason="O365 app-only test tenant settings are not configured.")
async def test_live_cc_bcc_inline_image(tmp_path):
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"\x89PNG\r\n\x1a\nFEAT-004 live test logo bytes")

    async with Notify("office365", auth_flow="client_credentials", sender=O365_TEST_SENDER) as mail:
        results = await mail.send(
            recipient=[_recipient()],
            cc=[O365_TEST_RECIPIENT],
            bcc=[O365_TEST_RECIPIENT],
            subject="FEAT-004 live test: CC/BCC + inline image",
            message='<p>Live integration test - inline image.</p><img src="cid:logo">',
            inline_images={"logo": str(logo)},
        )
    assert len(results) == 1
    assert results[0].success is True


@pytest.mark.skipif(
    not _obo_configured,
    reason="O365 on_behalf_of test tenant settings (incl. a pre-issued O365_TEST_USER_ASSERTION) are not configured.",
)
async def test_live_obo_send():
    async with Notify("office365", auth_flow="on_behalf_of") as mail:
        results = await mail.send(
            recipient=[_recipient()],
            subject="FEAT-004 live test: On-Behalf-Of send",
            message="<p>Live integration test - On-Behalf-Of.</p>",
            user_assertion=O365_TEST_USER_ASSERTION,
        )
    assert len(results) == 1
    assert results[0].success is True


@pytest.mark.skipif(
    not _delegated_configured,
    reason="O365 delegated test tenant settings are not configured, or the token "
    "store was not pre-seeded via `python -m notify.providers.office365.login`.",
)
async def test_live_delegated_silent_after_seed():
    # Assumes `python -m notify.providers.office365.login --username <user>`
    # already seeded the configured token store (file/redis) out of band —
    # this test proves the silent, non-interactive refresh path only.
    async with Notify("office365", auth_flow="delegated", username=O365_TEST_DELEGATED_USERNAME) as mail:
        results = await mail.send(
            recipient=[_recipient()],
            subject="FEAT-004 live test: delegated silent send",
            message="<p>Live integration test - delegated silent cache.</p>",
        )
    assert len(results) == 1
    assert results[0].success is True


@pytest.mark.skipif(
    not _denied_configured,
    reason="O365 send-as-denied test tenant settings (O365_TEST_DENIED_SENDER) are not configured.",
)
async def test_live_send_as_denied_raises():
    from notify.exceptions import NotifyAuthError

    async with Notify("office365", auth_flow="client_credentials", sender=O365_TEST_SENDER) as mail:
        with pytest.raises(NotifyAuthError):
            await mail.send(
                recipient=[_recipient()],
                subject="FEAT-004 live test: send-as denied",
                message="<p>Live integration test - should be denied.</p>",
                from_address=O365_TEST_DENIED_SENDER,
            )
