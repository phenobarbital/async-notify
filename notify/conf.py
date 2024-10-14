# Import Config Class
from pathlib import Path
from navconfig import BASE_DIR, config


# TEMPLATE SYSTEM
if not (template_dir := config.get('TEMPLATE_DIR')):
    TEMPLATE_DIR = BASE_DIR.joinpath("templates")
else:
    TEMPLATE_DIR = Path(template_dir).resolve()


# Notify Worker (Consumer)
REDIS_HOST = config.get('REDIS_HOST', fallback='localhost')
REDIS_PORT = config.getint('REDIS_PORT', fallback=6379)
NOTIFY_DB = config.getint('NOTIFY_DB', fallback=4)
NOTIFY_REDIS = f"redis://{REDIS_HOST}:{REDIS_PORT}/{NOTIFY_DB}"
NOTIFY_CHANNEL = config.get('NOTIFY_CHANNEL', fallback='NotifyChannel')
NOTIFY_DEFAULT_HOST = config.get('NOTIFY_DEFAULT_HOST', fallback='0.0.0.0')
NOTIFY_DEFAULT_PORT = config.get('NOTIFY_DEFAULT_PORT', fallback=8991)
NOTIFY_QUEUE_SIZE = config.getint('NOTIFY_QUEUE_SIZE', fallback=8)
## Queue Consumed Callback
NOTIFY_QUEUE_CALLBACK = config.get(
    'NOTIFY_QUEUE_CALLBACK', fallback=None
)

## Email
EMAIL_SMTP_USERNAME = config.get("stmp_host_user")
EMAIL_SMTP_PASSWORD = config.get("stmp_host_password")
EMAIL_SMTP_PORT = config.get("smtp_port", fallback=587)
EMAIL_SMTP_HOST = config.get("stmp_host")

## Telegram:
# Telegram credentials
TELEGRAM_BOT_TOKEN = config.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = config.get("TELEGRAM_CHAT_ID")

## Slack
SLACK_APP_ID = config.get("SLACK_APP_ID")
SLACK_CLIENT_ID = config.get("SLACK_CLIENT_ID")
SLACK_CLIENT_SECRET = config.get("SLACK_CLIENT_SECRET")
SLACK_SIGNING_SECRET = config.get("SLACK_SIGNING_SECRET")
# Bot information:
SLACK_BOT_TOKEN = config.get("SLACK_BOT_TOKEN")
SLACK_DEFAULT_CHANNEL = config.get("SLACK_DEFAULT_CHANNEL")
SLACK_TEAM_ID = config.get("SLACK_TEAM_ID")

# Jabber Service
JABBER_JID = config.get("JABBER_JID")
JABBER_PASSWORD = config.get("JABBER_PASSWORD")

# Gmail
GMAIL_USERNAME = config.get("GMAIL_USERNAME")
GMAIL_PASSWORD = config.get("GMAIL_PASSWORD")

# Office 365
O365_CLIENT_ID = config.get("O365_CLIENT_ID")
O365_CLIENT_SECRET = config.get("O365_CLIENT_SECRET")
O365_TENANT_ID = config.get("O365_TENANT_ID")
O365_USER = config.get("O365_USER")
O365_PASSWORD = config.get("O365_PASSWORD")

# Microsoft Teams
MS_TEAMS_TENANT_ID = config.get("MS_TEAMS_TENANT_ID")
MS_TEAMS_CLIENT_ID = config.get("MS_TEAMS_CLIENT_ID")
MS_TEAMS_CLIENT_SECRET = config.get("MS_TEAMS_CLIENT_SECRET")
MS_TEAMS_DEFAULT_TEAMS_ID = config.get("MS_TEAMS_DEFAULT_TEAMS_ID")
MS_TEAMS_DEFAULT_CHANNEL_ID = config.get("MS_TEAMS_DEFAULT_CHANNEL_ID")
MS_TEAMS_DEFAULT_WEBHOOK = config.get("MS_TEAMS_DEFAULT_WEBHOOK")

# Sendgrid
SENDGRID_USER = config.get("SENDGRID_USER")
SENDGRID_KEY = config.get("SENDGRID_KEY")

## Amazon AWS SMTP:
# Amazon AWS
AWS_EMAIL_USER = config.get("aws_email_user")
AWS_EMAIL_PASSWORD = config.get("aws_email_password")
AWS_EMAIL_HOST = config.get(
    "aws_email_host", fallback="email-smtp.us-east-1.amazonaws.com"
)
AWS_EMAIL_PORT = config.get("aws_email_port", fallback=587)
AWS_EMAIL_ACCOUNT = config.get("aws_email_account")

AWS_ACCESS_KEY_ID = config.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = config.get("AWS_SECRET_ACCESS_KEY")
AWS_REGION_NAME = config.get("AWS_REGION_NAME")
AWS_SENDER_EMAIL = config.get("AWS_SENDER_EMAIL")

# OneSignail
ONESIGNAL_PLAYER_ID = config.get("ONESIGNAL_PLAYER_ID")
ONESIGNAL_OS_APP_ID = config.get("ONESIGNAL_OS_APP_ID")
ONESIGNAL_OS_API_KEY = config.get("ONESIGNAL_OS_API_KEY")

# Twilio credentials
TWILIO_ACCOUNT_SID = config.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = config.get("TWILIO_AUTH_TOKEN")
TWILIO_PHONE = config.get("TWILIO_PHONE")

# Twitter Tweets:
TWITTER_ACCESS_TOKEN = config.get("TWITTER_ACCESS_TOKEN")
TWITTER_TOKEN_SECRET = config.get("TWITTER_TOKEN_SECRET")
TWITTER_CONSUMER_KEY = config.get("TWITTER_CONSUMER_KEY")
TWITTER_CONSUMER_SECRET = config.get("TWITTER_CONSUMER_SECRET")


try:
    from settings.settings import *  # pylint: disable=W0614,W0401
except ImportError:
    pass
