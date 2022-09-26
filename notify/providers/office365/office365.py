# -*- coding: utf-8 -*-
"""
o365.

Office 365 Email-based provider
"""
from typing import (
    Callable
)
from notify.providers.abstract import ProviderEmail
from notify.settings import (
    O365_CLIENT_ID,
    O365_CLIENT_SECRET,
    O365_TENANT_ID,
    O365_USER,
    O365_PASSWORD
)
from notify.models import Actor
from navconfig.logging import logging

logging.getLogger('requests_oauthlib').setLevel(logging.CRITICAL)
# 3rd party Office 365 support
from O365 import (
    Account,
    Connection,
    MSOffice365Protocol,
    Message
)

class Office365(ProviderEmail):
    """ O365-based Email Provider
    :param client-id: Email client id
    :param client-secret: Email client secret
    :param client-email: actor email
    """
    provider = 'office365'
    blocking: bool = True

    def __init__(
            self,
            client_id: str = None,
            client_secret: str = None,
            tenant_id: str = None,
            username: str = None,
            password: str = None,
            *args,
            **kwargs
        ):
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

        if self.client_id is None or self.client_secret is None:
            raise RuntimeWarning(
                f'to send emails via {self.name} you need to configure client id & client secret. \n'
                'Either send them as function argument via key id and secret or setup variables \n'
                'as `O365_CLIENT_ID` & `O365_CLIENT_SECRET`.'
            )

    def connect(self):
        """
        """
        self.protocol = MSOffice365Protocol()
        # scopes_graph = self.protocol.get_scopes_for('Mail.ReadWrite')
        scopes = ["https://graph.microsoft.com/.default"]
        if self.username is not None:
            self.account = Connection(
                credentials=(self.client_id, self.client_secret),
                auth_flow_type='credentials',
                tenant_id=self.tenant_id
            )
        else:
            self.account = Account(
                credentials=(self.client_id, self.client_secret),
                auth_flow_type='credentials',
                tenant_id=self.tenant_id,
                protocol=self.protocol
            )
            result = self.account.authenticate(scope=scopes)
            print('OFFICE635 Auth: ', result)
        try:
            return self.account
        except Exception as e:
            return e

    async def close(self):
        pass

    def _render(self, to: Actor, subject: str, content: str, **kwargs):
        """
        """
        msg = content
        if self._template:
            templateargs = {
                "recipient": to,
                "username": to,
                "message": content,
                "content": content,
                **kwargs
            }
            msg = self._template.render(**templateargs)
        else:
            try:
                msg = kwargs['body']
            except KeyError:
                msg = content
        # email message
        if self.username is not None:
            # using basic auth instead API
            message = Message(
                auth=(self.username, self.password),
                protocol=self.protocol,
                con=self.account
            )
        else:
            message = self.account.new_message()
        message.to.add(to.account['address'])
        message.subject = subject
        message.body = msg
        return message

    async def _send(self, to: Actor, message: str, subject: str,  **kwargs):
        """
        _send.
        Logic associated with the construction of notifications
        """
        # making email connnection
        try:
            message = self._render(to, subject, message, **kwargs)
            status = message.send()
            logging.debug(status)
            return status
        except Exception as e:
            print(e)
            raise RuntimeError(f"{e}") from e
