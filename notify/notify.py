import importlib
from navconfig.logging import logger
from .providers.base import ProviderBase
from .exceptions import ProviderError, NotifyException
from .conf import TEMPLATE_DIR
from .templates import TemplateParser


PROVIDERS = {}
TemplateEnv = None

class Notify:
    """Notify

        Factory object for getting a new Notification Provider.
    Args:
        provider (str): Name of the provider.

    Raises:
        ProviderError: when a driver cannot be loaded.
        NotSupported: when a method is not supported.
    Returns:
        ProviderBase: a Notify Provider.
    """
    def __new__(cls: type['ProviderBase'], provider: str, *args, **kwargs):
        _provider = None
        try:
            if provider not in PROVIDERS:
                PROVIDERS[provider] = LoadProvider(provider)
            obj = PROVIDERS[provider]
            _provider = obj(*args, **kwargs)
            logger.debug(
                f":: Load Provider: {provider}"
            )
            return _provider
        except Exception as ex:
            logger.critical(
                f"Cannot Load provider {provider}: {ex}"
            )
            raise ProviderError(
                message=f"Cannot Load provider {provider}: {ex}"
            ) from ex

    @classmethod
    def provider(cls: type['ProviderBase'], provider: str, *args, **kwargs):
        try:
            if provider not in PROVIDERS:
                PROVIDERS[provider] = LoadProvider(provider)
            obj = PROVIDERS[provider]
            _provider = obj(*args, **kwargs)
            logger.debug(
                f":: Loaded Provider: {provider}"
            )
            return _provider
        except Exception as ex:
            logger.critical(
                f"Cannot Load provider {provider}: {ex}"
            )
            raise ProviderError(
                message=f"Cannot Load provider {provider}: {ex}"
            ) from ex


def LoadProvider(provider: str):
    """
    loadProvider.
    Dynamically load a Notify provider
    """
    try:
        classpath = f"notify.providers.{provider}"
        module = importlib.import_module(classpath, package="providers")
        return getattr(module, provider.capitalize())
    except ImportError:
        try:
            obj = __import__(classpath, fromlist=[provider])
            return obj
        except ImportError as exc:
            raise NotifyException(
                f"Error: No Provider {provider} was Found: {exc}"
            ) from exc


if __name__ == "notify.notify":
    # loading template parser:
    TemplateEnv = TemplateParser(
        directory=TEMPLATE_DIR
    )
