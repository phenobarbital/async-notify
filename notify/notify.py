import logging
import importlib
from .exceptions import ProviderError, notifyException

PROVIDERS = {}

class Notify(object):
    """Notify

        Factory object for getting a new Notification Provider.
    Args:
        provider (str): Name of the provider.

    Raises:
        ProviderError: _description_
        ProviderError: when a driver cannot be loaded.

    Returns:
        _type_: _description_
    """
    _provider = None
    _name = ''
    _config = None

    def __new__(cls, provider: str = None, *args, **kwargs):
        cls._provider = None
        if provider is not None:
            cls._provider = provider
            try:
                obj = PROVIDERS[provider]
                cls._provider = obj(*args, **kwargs)
                logging.debug('Load Provider: {}'.format(provider))
            except Exception as err:
                logging.exception("Cannot Load provider {}".format(provider))
                raise ProviderError(
                    message = "Cannot Load provider {}".format(provider)
                )
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
            logging.exception("Cannot Load provider {}".format(cls._name))
            raise ProviderError(message = "Cannot Load provider {}".format(cls._name))
        finally:
            return cls._provider
        

def LoadProvider(provider):
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