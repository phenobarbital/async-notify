# -*- coding: utf-8 -*-
import os
import sys
import pkgutil
from pathlib import Path
import asyncio
import importlib
import logging

from notify.settings import TEMPLATE_DIR
from notify.templates import TemplateParser
from .exceptions import ProviderError, notifyException

PROVIDERS = {}
TemplateEnv = None

class Notify(object):
    _provider = None
    _name = ''
    _config = None

    def __new__(cls, provider=None, *args, **kwargs):
        cls._provider = None
        if provider is not None:
            cls._provider = provider
            try:
                obj = PROVIDERS[provider]
                cls._provider = obj(*args, **kwargs)
                logging.debug('Load Provider: {}'.format(provider))
            except Exception as err:
                print(err)
                logging.error("Cannot Load provider {}".format(provider))
                raise ProviderError(message = "Cannot Load provider {}".format(provider))
            finally:
                return cls._provider
        else:
            return super(Notify, cls).__new__(cls, *args, **kwargs)

    def provider(cls, provider=None, *args, **kwargs):
        cls._provider = None
        cls._name = provider
        try:
            obj = PROVIDERS[provider]
            cls._provider = obj(*args, **kwargs)
            logging.debug('Load Provider: {}'.format(cls._name))
        except Exception as err:
            #TODO: try to load the new provider.
            print(err)
            logging.error("Cannot Load provider {}".format(cls._name))
            raise ProviderError(message = "Cannot Load provider {}".format(cls._name))
        finally:
            return cls._provider


def loadProvider(provider):
    """
    loadProvider.

    Dynamically load a defined provider
    """
    try:
        # try to using importlib
        classpath = 'notify.providers.{provider}'.format(provider=provider)
        module = importlib.import_module(classpath, package='providers')
        obj = getattr(module, provider.capitalize())
        return obj
    except ImportError:
        try:
            obj = __import__(classpath, fromlist=[provider])
            return obj
        except ImportError:
            raise notifyException(f'Error: No Provider {provider} was Found')
            return False


if __name__ == "notify":
    path = Path(__file__).parent.joinpath('providers')
    # directory for notify providers
    for (_, name, _) in pkgutil.iter_modules([path]):
        cls = loadProvider(name)
        PROVIDERS[name] = cls
    # loading template parser:
    TemplateEnv = TemplateParser(
        directory=TEMPLATE_DIR
    )
