---
id: F002
query_id: Q002
type: read
intent: Read the Notify factory to understand current provider dispatch and the PROVIDERS registry
executed_at: 2026-09-29T16:00:00Z
parent_id: null
depth: 0
---

# F002 — The Notify factory ALREADY lazy-imports providers via importlib

## Summary

`LoadProvider` resolves a provider by `importlib.import_module(f"notify.providers.{provider}")`
at call time and memoises the class in the module-level `PROVIDERS` dict. Both
`Notify.__new__` and `Notify.provider()` go through it. Provider modules — and
therefore their third-party SDKs — are imported only on first use of that
provider. The requested "lazy-import de providers" is already implemented.
`notify/notify.py` also already uses PEP 562 `__getattr__` to defer building the
shared `TemplateEnv`.

## Citations

- path: `notify/notify.py`
  lines: 70-86
  symbol: `LoadProvider`
  excerpt: |
    def LoadProvider(provider: str):
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

- path: `notify/notify.py`
  lines: 31-41
  symbol: `Notify.__new__`
  excerpt: |
    def __new__(cls, provider: str, *args, **kwargs):
        if provider not in PROVIDERS:
            PROVIDERS[provider] = LoadProvider(provider)
        obj = PROVIDERS[provider]
        _provider = obj(*args, **kwargs)

- path: `notify/notify.py`
  lines: 1-10
  symbol: module imports
  excerpt: |
    import importlib
    from navconfig.logging import logger
    from .conf import TEMPLATE_DIR
    from .exceptions import NotifyException, ProviderError
    from .providers.base import ProviderBase
    from .templates import TemplateParser

    PROVIDERS = {}

- path: `notify/notify.py`
  lines: 89-116
  symbol: `__getattr__`
  excerpt: |
    def __getattr__(name: str):
        if name == "TemplateEnv":
            global _TEMPLATE_ENV
            if _TEMPLATE_ENV is None:
                _TEMPLATE_ENV = TemplateParser(directory=TEMPLATE_DIR)
            return _TEMPLATE_ENV

## Notes

`from .conf import TEMPLATE_DIR` at line 5 is only consumed inside `__getattr__`
(line 109) — a module-level import serving a deliberately-lazy consumer. Same for
`TemplateParser` at line 8. Both are deferrable. See F008.
