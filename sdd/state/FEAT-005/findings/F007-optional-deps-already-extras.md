---
id: F007
query_id: Q007
type: read
intent: Determine which provider dependencies are hard requirements vs optional extras
executed_at: 2026-09-29T16:00:00Z
parent_id: null
depth: 0
---

# F007 — Provider SDKs are already optional extras; three core deps are provider-only

## Summary

`pyproject.toml` already separates provider SDKs into extras (`telegram`,
`push`, `google`, `azure`, `templates`, `default`, `all`). Core `dependencies`
carries 8 packages. Three of them are used by **exactly one provider each** and
are therefore mis-classified as core: `emoji` (telegram only), `aiobotocore`
(ses only), `aiosmtplib` (the mail base only). `pillow` appears in core
dependencies but **no `notify/` module imports PIL at all**. Conversely several
installed providers have *no* extra covering them (`twilio`, `slixmpp`/xmpp and
`slack_bolt`/`slack_sdk` appear only inside `all` or `default`).

## Citations

- path: `pyproject.toml`
  lines: 36-45
  symbol: `[project] dependencies`
  excerpt: |
    dependencies = [
      "aiosmtplib>=5.0",
      "python-datamodel>=0.3.12",
      "navconfig[default]>=2.2.0",
      "jinja2>=3.1.4",
      "cloudpickle>=3.1.0",
      "emoji>=1.7.0",
      "aiobotocore>=2.15.2",
      "pillow>=8.3.2",
    ]

- path: `pyproject.toml`
  lines: 47-80
  symbol: `[project.optional-dependencies]`
  excerpt: |
    uvloop = ["uvloop>=0.20.0; sys_platform != 'win32'"]
    default = ["aiogram>=3.14.0", "slack_bolt>=1.18.0"]
    telegram = ["aiogram>=3.14.0", "moviepy>=2.2.1"]
    push = ["onesignal-sdk>=2.0.0"]
    google = ["gmail>=0.6.3", "google-auth>=2.6.0", ...]
    azure = ["pyo365", "o365>=2.0.37,<2.1", "msal", ...]

- path: `notify/providers/telegram/Telegram.py`
  lines: 4
  symbol: import
  excerpt: |
    import emoji

- path: `notify/providers/ses/ses.py`
  lines: 4-5
  symbol: import
  excerpt: |
    from aiobotocore.session import get_session
    from botocore.exceptions import ClientError

- path: `notify/server/client.py`
  lines: n/a
  symbol: cloudpickle usage
  excerpt: |
    (cloudpickle is used only by notify/server/client.py and notify/server/server.py)

## Notes

`emoji`, `aiobotocore` and `pillow` are not imported by anything reachable from
`import notify`, so demoting them to extras changes **install** weight, not
import time. `cloudpickle` is server-only and equally demotable.

**Verified**: `grep -rn "PIL" notify --include=*.py` returns only
`notify/models.py` hits on the unrelated `activityImage` Teams-card field —
no module imports Pillow. `pillow>=8.3.2` in core `dependencies` is dead weight.
