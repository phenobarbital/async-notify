# -*- coding: utf-8 -*-
from notify.settings import (
    EMAIL_SMTP_USERNAME,
    EMAIL_SMTP_PASSWORD,
    EMAIL_SMTP_HOST,
    EMAIL_SMTP_PORT
)
from notify.providers.abstract import ProviderEmail


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

        # server information
        if hostname:
            self._host = hostname
        else:
            if not self._host: # already configured
                try:
                    self._host = kwargs['hostname']
                except KeyError:
                    self._host = EMAIL_SMTP_HOST

        if port:
            self._port = port
        else:
            if not self._port:
                try:
                    self._port = kwargs['port']
                except KeyError:
                    self._port = EMAIL_SMTP_PORT

        # connection related settings
        if username:
            self.username = username
        if self.username is None:
            self.username = EMAIL_SMTP_USERNAME
        
        if password:
            self.password = password
        if self.password is None:
            self.password = EMAIL_SMTP_PASSWORD

        if self.username is None or self.password is None:
            raise RuntimeWarning(
                'to send messages via **{0}** you need to configure user & password. \n'
                'Either send them as function argument via key \n'
                '`username` & `password` or set up env variable \n'
                'as `EMAIL_USERNAME` & `EMAIL_PASSWORD`.'.format(self._name)
            )
        try:
            # sent from another account
            if 'account' in kwargs:
                self.actor = kwargs['account']
            else:
                self.actor = self.username
        except KeyError:
            self.actor = self.username