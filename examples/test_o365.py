"""Send mail through Microsoft Graph via the office365 provider (FEAT-004).

This is a manual/example script, not a test — replace the placeholder
credentials and addresses with real values (or navconfig `O365_*`
settings) before running.

Never commit real client secrets, certificate passwords, or user tokens.
"""

import asyncio

from notify import Notify
from notify.models import Actor

user = {
    "name": "Jesus Lara",
    "account": {
        "address": "jesuslarag@gmail.com",
    },
}
user2 = {
    "name": "Jesus Lara",
    "account": {
        "provider": "email",
        "address": "jesuslara@devel.com.ve",
    },
}


async def send_mail() -> None:
    recipients = [Actor(**user), Actor(**user2)]

    # App-only (client_credentials): sends as a shared mailbox (`sender=`).
    # Client id/secret/tenant id can also come from the O365_CLIENT_ID /
    # O365_CLIENT_SECRET / O365_TENANT_ID navconfig settings instead of
    # being passed explicitly here.
    mail = Notify(
        "office365",
        auth_flow="client_credentials",
        client_id="CLIENT_ID",
        client_secret="CLIENT_SECRET",
        tenant_id="TENANT_ID",
        sender="noreply@contoso.com",
    )
    async with mail as m:
        result = await m.send(
            recipient=recipients,
            subject="Epale, vente a jugar bolas criollas!",
            event_name="Partido de bolas Criollas",
            event_address="Bolodromo Caucagua",
            template="email_applied.html",
        )
        print("THIS > ", result)


if __name__ == "__main__":
    asyncio.run(send_mail())
