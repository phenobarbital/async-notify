"""
Outlook Client.
"""
from collections.abc import Callable
import msal
import base64
import aiofiles
from pathlib import Path
from office365.graph_client import GraphClient
from navconfig.logging import logging
from notify.providers.mail import ProviderEmail
from notify.models import Actor
from notify.conf import (
    O365_CLIENT_ID,
    O365_CLIENT_SECRET,
    O365_TENANT_ID,
    O365_USER,
    O365_PASSWORD,
)

class Outlook(ProviderEmail):
    """Outlook-based Email Provider
    :param client-id: Email client id
    :param client-secret: Email client secret
    :param client-email: actor email
    """

    provider = "outlook"
    blocking: str = 'asyncio'

    def __init__(
        self,
        *args,
        username: str = None,
        password: str = None,
        use_credentials: bool = True,
        client_id: str = None,
        client_secret: str = None,
        tenant_id: str = None,

        **kwargs,
    ):
        self.authenticate: bool = False
        self.account: Callable = None
        self.protocol: Callable = None
        self._attachments: dict = {}
        super(Outlook, self).__init__(*args, **kwargs)

        # connection related settings
        self.client_id = client_id if client_id is not None else O365_CLIENT_ID

        self.client_secret = client_secret
        if self.client_secret is None:
            self.client_secret = O365_CLIENT_SECRET

        # tenant id
        self.tenant_id = tenant_id if tenant_id is not None else O365_TENANT_ID
        ## application scopes:
        self.scopes = ["https://graph.microsoft.com/.default"]
        # username and password:
        self.username = username
        self.password = password
        self.use_credentials = use_credentials
        if use_credentials is True:
            if not self.username:
                self.username = O365_USER
            if not self.password:
                self.password = O365_PASSWORD

        if self.client_id is None or self.client_secret is None:
            raise RuntimeWarning(
                f"to send emails via {self.name} you need to configure client id & client secret. \n"
                "Either send them as function argument via key id and secret or setup variables \n"
                "as `O365_CLIENT_ID` & `O365_CLIENT_SECRET`."
            )

    def acquire_token(self):
        """
        Acquire token via MSAL
        """
        authority_url = f'https://login.microsoftonline.com/{self.tenant_id}'
        app = msal.ConfidentialClientApplication(
            authority=authority_url,
            client_id=self.client_id,
            client_credential=self.client_secret
        )
        return app.acquire_token_for_client(scopes=self.scopes)

    def acquire_token_by_username(self):
        authority_url = f'https://login.microsoftonline.com/{self.tenant_id}'
        app = msal.PublicClientApplication(
            authority=authority_url,
            client_id=self.client_id,
        )
        return app.acquire_token_by_username_password(
            username=self.username,
            password=self.password,
            scopes=self.scopes
        )

    async def add_attachment(self, filename):
        ## Add an attachment into Mail Message as base64 encoded content.
        if isinstance(filename, str):
            filename = Path(filename).resolve()
        if not filename.exists():
            raise FileNotFoundError(
                f"Attachment Error: {filename} does not exist."
            )
        content = b''
        async with aiofiles.open(str(filename), "rb") as f:
            content = await f.read()
        content = base64.b64encode(content).decode()
        self._attachments[filename.name] = content

    async def connect(self, **kwargs):
        """Connect.
        Making a connection using MS Office 365 Protocol.
        """
        try:
            if self.use_credentials is True:
                self.client = GraphClient(self.acquire_token_by_username)
            else:
                self.client = GraphClient(self.acquire_token)
        except Exception as exc:
            self.logger.error(
                f"Error during authentication: {exc}"
            )

    async def _render_(self, to: Actor, message: str = None, subject: str = None, **kwargs):
        """ """
        if self._template:
            templateargs = {
                "recipient": to,
                "username": to,
                "message": message,
                "content": message,
                **kwargs,
            }
            msg = await self._template.render_async(**templateargs)
        else:
            try:
                msg = kwargs["body"]
            except KeyError:
                msg = message
        # email message
        content = self.client.me.send_mail(
            subject=subject,
            body=msg,
            to_recipients=[to.account.address]
        )
        content.body.contentType = 'html'
        if self._attachments:
            for file, msg in self._attachments.items():
                content.add_file_attachment(file, base64_content=msg)
        return content

    async def _send_(self, to: Actor, message: str, subject: str, **kwargs):
        """
        _send_.
        Logic associated with the construction of notifications
        """
        # making email connnection
        try:
            message = await self._render_(to, message, subject, **kwargs)
        except (TypeError, ValueError) as exc:
            print(exc)
            return False
        try:
            result = message.execute_query()
            return result
        except Exception as exc:
            print('Error: ', exc)
            logging.exception(exc, stack_info=True)
            raise RuntimeError(f"{exc}") from exc
