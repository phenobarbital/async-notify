# -*- coding: utf-8 -*-
"""
Amazon AWS Email.

Sending amazon Emails using SMTP services
"""


from notify.settings import (
    AWS_EMAIL_USER,
    AWS_EMAIL_ACCOUNT,
    AWS_EMAIL_PASSWORD,
    AWS_EMAIL_HOST,
    AWS_EMAIL_PORT
)
from notify.providers.abstract import ProviderEmail


class Aws_email(ProviderEmail):
    """ AWS-based Email Provider
    Args:
        :param username: Email client username
        :param password: Email client password
    """
    provider = 'aws_email'
    blocking: bool = False
    

    def __init__(self, hostname: str = None, port: str = None, username: str = None, password: str = None, *args, **kwargs):
        
        self.username = None
        self.password = None
        
        if hostname:
            self._host = hostname
        try:
            self._host = kwargs['host']
        except KeyError:
            self._host = AWS_EMAIL_HOST
        if not self._host:
            self._host = 'email-smtp.eu-west-1.amazonaws.com' # default

        try:
            self._port = kwargs['port']
        except KeyError:
            self._port = AWS_EMAIL_PORT
        if not self._port:
            self._port = 587
 
        super(Aws_email, self).__init__(*args, **kwargs)

        # connection related settings
        if username:
            self.username = username
        if self.username is None:
            self.username =     AWS_EMAIL_USER

        if password:
            self.password = password
        if self.password is None:
            self.password = AWS_EMAIL_PASSWORD
            
        try:
            # sent from another account
            if 'account' in kwargs:
                self.actor = kwargs['account']
            else:
                self.actor = AWS_EMAIL_ACCOUNT
        except KeyError:
            self.actor = AWS_EMAIL_ACCOUNT