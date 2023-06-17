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

# gmail
GMAIL_USERNAME = config.get("GMAIL_USERNAME")
GMAIL_PASSWORD = config.get("GMAIL_PASSWORD")

try:
    from settings.settings import *  # pylint: disable=W0614,W0401
except ImportError:
    pass
