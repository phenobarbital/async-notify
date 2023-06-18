# -*- coding: utf-8 -*-
"""
o365.

Office 365 Email-based provider
"""
from collections.abc import Callable
from datetime import datetime
# 3rd party Office 365 support
from O365 import (
    Account,
    MSOffice365Protocol,
    Message,
    Connection,
    FileSystemTokenBackend
)
from navconfig import BASE_DIR
from navconfig.logging import logging
from notify.providers.mail import ProviderEmail
from notify.exceptions import NotifyAuthError
from notify.models import Actor
from notify.conf import (
    O365_CLIENT_ID,
    O365_CLIENT_SECRET,
    O365_TENANT_ID,
    O365_USER,
    O365_PASSWORD,
)


logging.getLogger("requests_oauthlib").setLevel(logging.CRITICAL)
logging.getLogger("O365.connection").setLevel(logging.CRITICAL)

class Office365(ProviderEmail):
    """O365-based Email Provider
    :param client-id: Email client id
    :param client-secret: Email client secret
    :param client-email: actor email
    """

    provider = "office365"
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
        super(Office365, self).__init__(*args, **kwargs)

        # connection related settings
        self.client_id = client_id if client_id is not None else O365_CLIENT_ID

        self.client_secret = client_secret
        if self.client_secret is None:
            self.client_secret = O365_CLIENT_SECRET

        # tenant id
        self.tenant_id = tenant_id if tenant_id is not None else O365_TENANT_ID

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

    async def connect(self, **kwargs):
        """Connect.
        Making a connection using MS Office 365 Protocol.
        """
        self.protocol = MSOffice365Protocol(**kwargs)
        credentials = (self.client_id, self.client_secret)
        # "https://graph.microsoft.com/.default",
        scopes = ["https://outlook.office.com/.default"]
        # first: check if credential file exists:
        o365_token = BASE_DIR.joinpath('.o365_token.txt')
        token_backend = FileSystemTokenBackend(
            token_path='.',
            token_filename='.o365_token.txt'
        )
        if not o365_token.exists():
            ## create a authorization code flow:
            self.account = Account(
                credentials=credentials,
                auth_flow_type="authorization",
                tenant_id=self.tenant_id,
                protocol=self.protocol,
                token_backend=token_backend
            )
            # This will print the URL to the console
            print(self.account.con.get_authorization_url(scopes))
            # After you have logged in in the browser, you need to paste the resulting URL back into the console
            result_url = input('Paste the result URL here: ')
            # This will save the token to a file
            self.account.con.request_token(result_url)
            self.mailbox = self.account.mailbox(
                resource=self.username
            )
            return self.account
        if self.use_credentials is True:
            self.account = Connection(
                credentials=credentials,
                auth_flow_type="credentials",
                tenant_id=self.tenant_id,
                protocol=self.protocol,
                token_backend=token_backend
            )
        else:
            self.account = Account(
                credentials=credentials,
                auth_flow_type="credentials",
                tenant_id=self.tenant_id,
                protocol=self.protocol,
                token_backend=token_backend
            )
            try:
                if result := self.account.authenticate(scopes=scopes):
                    self.authenticate = True
                    self.mailbox = self.account.mailbox(
                        resource=self.username
                    )
                    return self.account
                raise NotifyAuthError(
                    f"Unable to authenticate with Office 365 Backend: {result}"
                )
            except Exception as e:
                print(f"Error during authentication: {e}")
                # Token might be expired or invalid, delete it and start over
                o365_token.unlink()
                return await self.connect(**kwargs)

    async def close(self):
        pass

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
        if self.use_credentials is True:
            # using basic auth instead API
            content = Message(
                auth=(self.username, self.password),
                protocol=self.protocol,
                con=self.account,
            )
        else:
            content = self.mailbox.new_message()
        content.to.add(to.account.address)
        content.subject = subject
        content.body = msg
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
            result = message.send()
            return result
        except Exception as exc:
            print('Error: ', exc)
            logging.exception(exc, stack_info=True)
            raise RuntimeError(f"{exc}") from exc
