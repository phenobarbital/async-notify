# TASK-20: Configure Microsoft Graph mail and remove legacy dependencies

**Feature**: FEAT-004 — Mail Messages via Microsoft Graph (send-as & On-Behalf-Of)
**Spec**: `sdd/specs/mail-messages-graph.spec.md`
**Status**: pending
**Priority**: high
**Estimated effort**: S (< 2h)
**Depends-on**: none
**Assigned-to**: unassigned

---

## Context

The Graph provider needs navconfig-backed flow, sender, certificate, and encrypted-token-store settings. Its dependency extras must remove the unmaintained REST libraries. Implements spec §3 M9 and AC17.

## Scope

- Extend the existing Office365 config block with every `O365_*` setting specified in §3 M9.
- Update `azure` and `all` extras: retain MSAL and Graph packages, explicitly add `cryptography>=42.0`, and remove `pyo365`, `o365`, and `Office365-REST-Python-Client`.
- Regenerate `uv.lock` if the project workflow changes it.
- Add focused configuration/manifest assertions where existing test conventions support them.

**NOT in scope**: implementing token stores, consuming settings in a provider, or installing new packages outside the declared extras.

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `notify/conf.py` | MODIFY | Add Office365 Graph and token-store settings. |
| `pyproject.toml` | MODIFY | Replace legacy Azure dependencies. |
| `uv.lock` | MODIFY | Lockfile update if dependency resolution changes it. |
| `tests/test_office365_configuration.py` | CREATE | Focused defaults and dependency regression checks. |

## Codebase Contract (Anti-Hallucination)

### Verified Imports
```python
from pathlib import Path
from navconfig import BASE_DIR, config  # notify/conf.py:2-3
```

### Existing Signatures to Use
```python
# notify/conf.py:14-17,67-72
NOTIFY_REDIS = f"redis://{REDIS_HOST}:{REDIS_PORT}/{NOTIFY_DB}"
O365_CLIENT_ID = config.get("O365_CLIENT_ID")
O365_CLIENT_SECRET = config.get("O365_CLIENT_SECRET")
O365_TENANT_ID = config.get("O365_TENANT_ID")
O365_USER = config.get("O365_USER")
O365_PASSWORD = config.get("O365_PASSWORD")
```

### Does NOT Exist
- Direct `redis`, `aiofiles`, and `cryptography` entries are not currently declared in `pyproject.toml`.
- No provider may read these settings via `os.environ`.

## Implementation Notes

- Use `O365_TOKEN_STORE` default `memory`, `O365_TOKEN_STORE_TTL` default `0`, and `O365_TOKEN_ALLOW_UNENCRYPTED` default `False` exactly as specified.
- Set the default token-store directory from `BASE_DIR.joinpath(".o365")` and default Redis URL from `NOTIFY_REDIS`.
- Preserve unrelated optional-dependency groups.

## Acceptance Criteria

- [ ] All setting names and defaults match spec §3 M9.
- [ ] Legacy Office365 packages are absent from `azure` and `all` extras.
- [ ] `cryptography>=42.0` is explicit in both extras.
- [ ] Relevant configuration/manifest tests pass offline.
