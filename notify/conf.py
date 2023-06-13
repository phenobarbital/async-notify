# Import Config Class
from pathlib import Path
from navconfig import BASE_DIR, config


# TEMPLATE SYSTEM
if not (template_dir := config.get('TEMPLATE_DIR')):
    TEMPLATE_DIR = BASE_DIR.joinpath("templates")
else:
    TEMPLATE_DIR = Path(template_dir).resolve()

try:
    from settings.settings import *  # pylint: disable=W0614,W0401
except ImportError:
    pass
