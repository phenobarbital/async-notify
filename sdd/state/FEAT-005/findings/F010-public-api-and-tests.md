---
id: F010
query_id: Q011+Q013
type: grep
intent: Find public re-exports and tests that a lazy refactor must not break
executed_at: 2026-09-29T16:00:00Z
parent_id: null
depth: 0
---

# F010 — Small public surface; tests import provider classes by full path

## Summary

The only package-level `__all__` is `("Notify", "ProviderType")` in
`notify/__init__.py`. Tests reach providers by **full module path**
(`from notify.providers.outlook import Outlook`), never via a package-level
re-export — so adding PEP 562 laziness at the package root cannot break them.
`tests/test_templates_integration.py` already asserts on the lazy-import
behaviour of `notify.notify`, which makes it the natural home for new
startup-cost regression tests.

## Citations

- path: `notify/__init__.py`
  lines: 13-16
  symbol: `__all__`
  excerpt: |
    __all__ = (
        "Notify",
        "ProviderType",
    )

- path: `tests/test_templates_integration.py`
  lines: 72, 82, 108
  symbol: lazy-import assertions
  excerpt: |
    ``import notify.notify as nn`` resolves through the parent package's
        import notify as _notify_pkg
    import notify.notify as nn

- path: `tests/test_email_utf8.py`
  lines: 20-23
  symbol: direct provider imports
  excerpt: |
    from notify.providers import _mime_utils as mu
    from notify.providers.mail import ProviderEmail
    from notify.providers.smtp.smtp import SMTP
    from notify.providers.ses.ses import Ses

- path: `tests/test_outlook.py`
  lines: 2
  symbol: direct provider import
  excerpt: |
    from notify.providers.outlook import Outlook

## Notes

Test suite is 7 files. `pyproject.toml` sets `filterwarnings = ["error", …]`,
so any `DeprecationWarning` introduced by a lazy shim will fail the suite —
a useful guard rail, and a constraint on the implementation.
