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

# Facebook Messenger
FB_USER = config.get('FB_USER')
FB_PASSWORD = config.get('FB_PASSWORD')


# TEMPLATE SYSTEM
template_dir = config.get('TEMPLATE_DIR')
if not template_dir:
    TEMPLATE_DIR = BASE_DIR.joinpath('templates')
else:
    TEMPLATE_DIR = Path(template_dir).resolve()
