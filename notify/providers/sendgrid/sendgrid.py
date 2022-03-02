# -*- coding: utf-8 -*-
from notify.settings import (
    SENDGRID_USER,
    SENDGRID_KEY
)
from notify.providers.abstract import ProviderEmail


class Sendgrid(ProviderEmail):
    """
    Sendgrid.
    
    Sendgrid SMTP Client.
    """
    provider = 'sendgrid'
    blocking: bool = False
    

    def __init__(self, username: str = None, password: str = None, **kwargs):
        """

        """
        self._attachments: list = []
        self.force_tls: bool = True
        self.username = None
        self.password = None

        super(Sendgrid, self).__init__(**kwargs)

        # server information
        self._host = 'smtp.sendgrid.net'
        self._port = 587
        # connection related settings
        if username:
            self.username = username
        else:
            self.username = SENDGRID_USER
        
        if password:
            self.password = password
        else:
            self.password = SENDGRID_KEY

        try:
            # sent from another account
            if 'account' in kwargs:
                self.actor = kwargs['account']
            else:
                self.actor = self.username
        except KeyError:
            self.actor = self.username