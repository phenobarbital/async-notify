"""Send mail through the `outlook` alias of the Graph office365 provider (FEAT-004).

`outlook` is a backward-compatible alias of `office365` — same auth
flows, same `send()` behavior, plus the legacy `add_attachment(filename)`
queueing API. This is a manual/example script, not a test — replace the
placeholder credentials and addresses with real values (or navconfig
`O365_*` settings) before running.

Never commit real client secrets, certificate passwords, or user tokens.
"""

import asyncio

from navconfig import BASE_DIR

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

    mail = Notify(
        "outlook",
        auth_flow="client_credentials",
        client_id="CLIENT_ID",
        client_secret="CLIENT_SECRET",
        tenant_id="TENANT_ID",
        sender="noreply@contoso.com",
    )

    async with mail as m:
        # Queue a file for the next send() — merged in and cleared afterward.
        await m.add_attachment(BASE_DIR.joinpath("INSTALL"))
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
