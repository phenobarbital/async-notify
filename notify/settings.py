#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
- navigator_notify.settings
~~~~~~~~~~~~~~~~~~~~~~~~~~~
"""
from pathlib import Path
from navconfig import config, BASE_DIR

NOTIFY_DIR = Path(__file__).resolve().parent.parent

# config settings
NAVCONFIG = config
DEBUG = config.getboolean('DEBUG', fallback=True)

# OneSignail
ONESIGNAL_PLAYER_ID = config.get('ONESIGNAL_PLAYER_ID', fallback='')
ONESIGNAL_OS_APP_ID = config.get('ONESIGNAL_OS_APP_ID', fallback='')
ONESIGNAL_OS_API_KEY = config.get('ONESIGNAL_OS_API_KEY', fallback='')

# Sendgrid
SENDGRID_USER = config.get('SENDGRID_USER')
SENDGRID_KEY = config.get('SENDGRID_KEY')

# Amazon AWS
AWS_EMAIL_USER = config.get('aws_email_user')
AWS_EMAIL_PASSWORD = config.get('aws_email_password')
AWS_EMAIL_HOST = config.get(
    'aws_email_host', fallback='email-smtp.us-east-1.amazonaws.com'
)
AWS_EMAIL_PORT = config.get('aws_email_port', fallback=587)
AWS_EMAIL_ACCOUNT = config.get('aws_email_account')

# gmail
GMAIL_USERNAME = config.get('GMAIL_USERNAME')
GMAIL_PASSWORD = config.get('GMAIL_PASSWORD')

# Twilio credentials
TWILIO_ACCOUNT_SID = config.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = config.get('TWILIO_AUTH_TOKEN')
TWILIO_PHONE = config.get('TWILIO_PHONE')

# Office 365
O365_CLIENT_ID = config.get('O365_CLIENT_ID')
O365_CLIENT_SECRET = config.get('O365_CLIENT_SECRET')
O365_TENANT_ID = config.get('O365_TENANT_ID')
O365_USER = config.get('O365_USER')
O365_PASSWORD = config.get('O365_PASSWORD')

# Facebook Messenger
FB_USER = config.get('FB_USER')
FB_PASSWORD = config.get('FB_PASSWORD')

# Twitter Tweets:
TWITTER_ACCESS_TOKEN = config.get('TWITTER_ACCESS_TOKEN')
TWITTER_TOKEN_SECRET = config.get('TWITTER_TOKEN_SECRET')
TWITTER_CONSUMER_KEY = config.get('TWITTER_CONSUMER_KEY')
TWITTER_CONSUMER_SECRET = config.get('TWITTER_CONSUMER_SECRET')

# Jabber Service
JABBER_JID = config.get('JABBER_JID')
JABBER_PASSWORD = config.get('JABBER_PASSWORD')

# TEMPLATE SYSTEM
template_dir = config.get('TEMPLATE_DIR')
if not template_dir:
    TEMPLATE_DIR = BASE_DIR.joinpath('templates')
else:
    TEMPLATE_DIR = Path(template_dir).resolve()
