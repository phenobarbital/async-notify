import importlib
from navconfig.logging import Logger
from .providers.base import ProviderBase
from .exceptions import ProviderError, NotifyException

PROVIDERS = {}


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
            Logger.debug(
                f":: Load Provider: {provider}"
            )
            return _provider
        except Exception as ex:
            Logger.exception(
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
            Logger.debug(
                f":: Load Provider: {provider}"
            )
            return _provider
        except Exception as ex:
            Logger.exception(
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
