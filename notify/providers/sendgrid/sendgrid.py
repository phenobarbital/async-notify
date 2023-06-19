# -*- coding: utf-8 -*-
from notify.providers.mail import ProviderEmail
from notify.conf import SENDGRID_USER, SENDGRID_KEY


class Sendgrid(ProviderEmail):
    """
    Sendgrid.

    Sendgrid SMTP Client.
    TODO: migrate to API.
    """

    provider = "sendgrid"
    blocking: str = 'asyncio'

    def __init__(self, username: str = None, password: str = None, **kwargs):
        """ """
        self._attachments: list = []
        self.force_tls: bool = True

        super(Sendgrid, self).__init__(**kwargs)

        # server information
        self.host = "smtp.sendgrid.net"
        self.port = 587
        # connection related settings
        self.username = username
        if not self.username:
            self.username = SENDGRID_USER

        self.password = password
        if not self.password:
            self.password = SENDGRID_KEY

        try:
            # sent from another account
            if "account" in kwargs:
                self.actor = kwargs["account"]
            else:
                self.actor = self.username
        except KeyError:
            self.actor = self.username
