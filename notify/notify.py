from __future__ import annotations

import importlib
from pathlib import Path

from navconfig.logging import logger

from .exceptions import ProviderDependencyError, ProviderError
from .providers.base import ProviderBase

PROVIDERS = {}

PROVIDER_EXTRAS: dict[str, str] = {
    "gmail": "google",
    "office365": "azure",
    "onesignal": "push",
    "outlook": "azure",
    "ses": "ses",
    "slack": "slack",
    "teams": "azure",
    "telegram": "telegram",
    "twilio": "twilio",
    "xmpp": "xmpp",
}
"""Factory alias -> ``pyproject.toml`` extra that ships its SDK.

Keyed by the package directory name under ``notify/providers/`` — i.e. the
string callers pass to :class:`Notify` — never by ``cls.provider``, which
disagrees for ses/twilio/aws (verified: notify/providers/ses/ses.py,
notify/providers/twilio/twilio.py, notify/providers/aws/aws.py). Providers
whose only dependencies are core carry no entry.
"""

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
        except ProviderError:
            # Already precise (including ProviderDependencyError) — re-raise
            # unchanged so the subclass survives to the caller.
            raise
        except Exception as ex:
            logger.error(f"Cannot Load provider {provider}: {ex}")
            raise ProviderError(message=f"Cannot Load provider {provider}: {ex}") from ex

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
        except ProviderError:
            # Already precise (including ProviderDependencyError) — re-raise
            # unchanged so the subclass survives to the caller.
            raise
        except Exception as ex:
            logger.error(f"Cannot Load provider {provider}: {ex}")
            raise ProviderError(message=f"Cannot Load provider {provider}: {ex}") from ex


def _known_providers() -> tuple[str, ...]:
    """Return the sorted factory aliases discoverable on disk.

    Used only to build the "unknown provider" message. Never imports a
    provider module — it lists directories under ``notify/providers/``.

    Returns:
        Sorted package directory names, excluding private/dunder entries.
    """
    root = Path(__file__).parent / "providers"
    return tuple(
        sorted(
            entry.name
            for entry in root.iterdir()
            if entry.is_dir() and not entry.name.startswith("_") and (entry / "__init__.py").exists()
        )
    )


def LoadProvider(provider: str) -> type:
    """Dynamically load a Notify provider class by factory alias.

    Args:
        provider: Factory alias, i.e. the package directory name under
            ``notify/providers/`` (e.g. ``"telegram"``, ``"smtp"``).

    Returns:
        The provider class exported by ``notify.providers.<provider>``,
        resolved through that package's ``__all__``.

    Raises:
        ProviderDependencyError: The provider module exists but a third-party
            module it imports is missing. The message names the missing module
            and, when known, the extra that ships it.
        ProviderError: No such provider, or the package exports no resolvable
            provider class. The message lists known aliases.
    """
    classpath = f"notify.providers.{provider}"
    try:
        module = importlib.import_module(classpath)
    except ModuleNotFoundError as exc:
        missing = exc.name or ""
        if missing == classpath or missing.startswith(f"{classpath}."):
            known = ", ".join(_known_providers())
            raise ProviderError(message=f"No provider named {provider!r} was found. Known providers: {known}") from exc
        extra = PROVIDER_EXTRAS.get(provider)
        message = f"Provider {provider!r} requires the optional package {missing!r}, which is not installed."
        if extra:
            message += f" Install it with: pip install async-notify[{extra}]"
        raise ProviderDependencyError(message=message) from exc

    exported = getattr(module, "__all__", None)
    if exported:
        cls = getattr(module, exported[0], None)
        if cls is not None:
            return cls
    raise ProviderError(message=f"Package {classpath} does not export a resolvable provider class via __all__")


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
        from .conf import TEMPLATE_DIR  # noqa: PLC0415
        from .templates import TemplateParser  # noqa: PLC0415

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
