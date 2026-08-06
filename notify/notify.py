import importlib

from navconfig.logging import logger

from .conf import TEMPLATE_DIR
from .exceptions import NotifyException, ProviderError
from .providers.base import ProviderBase
from .templates import TemplateParser

PROVIDERS = {}

# Module-private memoisation slot for the lazy TemplateEnv singleton
# (PEP 562 __getattr__ below). Deliberately NOT named "TemplateEnv" —
# __getattr__ only fires for names absent from the module namespace.
_TEMPLATE_ENV: TemplateParser | None = None


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


def __getattr__(name: str):
    """PEP 562 module-level attribute hook.

    Builds the shared :class:`TemplateParser` on first access to
    ``TemplateEnv`` and memoises it, so importing :mod:`notify` never
    touches the filesystem.

    Args:
        name: The attribute being accessed on this module.

    Returns:
        The memoised :class:`TemplateParser` instance when ``name`` is
        ``"TemplateEnv"``.

    Raises:
        AttributeError: For any other undefined module attribute.
    """
    if name == "TemplateEnv":
        global _TEMPLATE_ENV
        if _TEMPLATE_ENV is None:
            if not TEMPLATE_DIR.exists():
                logger.warning(
                    "Notify: template directory %s does not exist; "
                    "TemplateEnv starts in memory-only mode.", TEMPLATE_DIR
                )
            _TEMPLATE_ENV = TemplateParser(directory=TEMPLATE_DIR)
        return _TEMPLATE_ENV
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Include the lazily-built ``TemplateEnv`` in module introspection."""
    return sorted([*globals().keys(), "TemplateEnv"])
