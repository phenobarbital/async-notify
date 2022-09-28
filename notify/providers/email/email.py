# -*- coding: utf-8 -*-
from notify.providers.mail import ProviderEmail
from .settings import (
    EMAIL_SMTP_USERNAME,
    EMAIL_SMTP_PASSWORD,
    EMAIL_SMTP_HOST,
    EMAIL_SMTP_PORT
)

class Email(ProviderEmail):
    """
    email.

    Basic SMTP Provider.
    """
    provider = 'email'
    blocking: bool = False


    def __init__(self, hostname: str = None, port: str = None, username: str = None, password: str = None, **kwargs):
        """

        """
        self._attachments: list = []
        self.force_tls: bool = True
        self.username = None
        self.password = None

        super(Email, self).__init__(**kwargs)
        # port
        self.host = hostname
        if not self.host: # already configured
            self.host = EMAIL_SMTP_HOST
        # port
        self.port = port
        if not self.port:
            self.port = EMAIL_SMTP_PORT

        # connection related settings
        self.username = username
        if self.username is None:
            self.username = EMAIL_SMTP_USERNAME

        self.password = password
        if self.password is None:
            self.password = EMAIL_SMTP_PASSWORD

        if self.username is None or self.password is None:
            raise RuntimeWarning(
                f'to send messages via **{self._name}** you need to configure user & password. \n'
                'Either send them as function argument via key \n'
                '`username` & `password` or set up env variable \n'
                'as `EMAIL_USERNAME` & `EMAIL_PASSWORD`.'
            )
        try:
            # sent from another account
            if 'account' in kwargs:
                self.actor = kwargs['account']
            else:
                self.actor = self.username
        except KeyError:
            self.actor = self.username
