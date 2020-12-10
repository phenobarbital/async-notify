"""
o365.

Office 365 Email-based provider
"""
# -*- coding: utf-8 -*-

from notify.providers import ProviderEmailBase, EMAIL
from notify.settings import O365_CLIENT_ID, O365_CLIENT_SECRET
from notify.exceptions import notifyException

# 3rd party Office 365 support
from pyo365 import Account
from pyo365 import MSGraphProtocol


class Office365(ProviderEmailBase):
    """ O365-based Email Provider
    :param client-id: Email client id
    :param client-secret: Email client secret
    :param client-email: actor email
    """
    provider = 'office365'
    provider_type = EMAIL
    account = None
    protocol = None

    def __init__(self, id=None, secret=None, actor=None, *args, **kwargs):
        """
        """
        super(Office365, self).__init__(*args, **kwargs)

        # connection related settings
        self.client_id = id
        if self.client_id is None:
            self.client_id = O365_CLIENT_ID

        self.client_secret = secret
        if self.client_secret is None:
            self.client_secret = O365_CLIENT_SECRET

        if self.client_id is None or self.client_secret is None:
            raise RuntimeWarning(
                'to send emails via {0} you need to configure client id & client secret. \n'
                'Either send them as function argument via key id and secret or setup variables \n'
                'as `O365_CLIENT_ID` & `O365_CLIENT_SECRET`.'.format(self.name)
            )
        self.actor = actor

    def _make_connection(self):
        """
        """
        self.account = Account(credentials=(self.client_id, self.client_secret))
        self.protocol = MSGraphProtocol(api_version='beta')
        try:
            result = self.account.authenticate(scopes=['basic', 'message_all'])
            print(result)
            return self.account
        except Exception as e:
            return e

    def _prepare_message(self, to, subject, context):
        """
        """
        super(Office365, self)._prepare_message(to, subject, context)
        message = self.account.new_message()
        message.to.add(to)
        message.subject = subject
        message.body = self.text_content
        #message.attachments.add(self.html_content)
        return message


    def send(self, recipient, verb, **kwargs):
        # making office 365 connnection
        try:
            self._make_connection()
        except Exception as e:
            raise RuntimeError(e)
        # get data
        message = self._prepare_message(recipient, verb, self.context)
        try:
            return message.send()
        except Exception as e:
            return e
