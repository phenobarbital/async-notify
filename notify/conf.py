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

try:
    from settings.settings import *  # pylint: disable=W0614,W0401
except ImportError:
    pass
