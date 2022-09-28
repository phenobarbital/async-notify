# -*- coding: utf-8 -*-
"""
Amazon AWS Email.

Sending Emails using Amazon SMTP services
"""
from notify.providers.mail import ProviderEmail
from .settings import (
    AWS_EMAIL_USER,
    AWS_EMAIL_ACCOUNT,
    AWS_EMAIL_PASSWORD,
    AWS_EMAIL_HOST,
    AWS_EMAIL_PORT
)

class Aws(ProviderEmail):
    """ AWS-based Email Provider
    Args:
        :param username: Email client username
        :param password: Email client password
    """
    provider = 'aws_email'
    blocking: bool = False


    def __init__(self, hostname: str = None, port: str = None, username: str = None, password: str = None, *args, **kwargs):

        super(Aws, self).__init__(*args, **kwargs)

        self.username = username
        self.password = password
        self.host = hostname
        self.port = port

        try:
            self.host = kwargs['host']
        except KeyError:
            pass
        if not self.host:
            self.host = self.host = AWS_EMAIL_HOST

        if not self.port:
            self.port = AWS_EMAIL_PORT

        # connection related settings
        if self.username is None:
            self.username =     AWS_EMAIL_USER

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
