# async-notify — Architectural Context

## What is async-notify
Asyncio-based Python library for sending notifications (messages) to users
across many transports: email (SMTP / Gmail / Office365 / Outlook / SES /
SendGrid), instant messaging (Slack, Teams, Telegram, XMPP, Zoom, Dialpad),
SMS/voice (Twilio, AWS), and push (OneSignal).

Transport-agnostic: every channel is reached through a uniform
`ProviderBase` interface, instantiated by the `Notify` factory.

Distribution name: `async-notify` · import package: `notify`.

---

## Core Abstractions (always inherit from these)

### Notify (factory)
Location: `notify/notify.py`
- `Notify("<provider>", **kwargs)` dynamically imports
  `notify.providers.<provider>` and returns a provider instance.
- Never import a concrete provider directly in user-facing code — go through
  `Notify` (or `Notify.provider()`), which caches loaded classes in the
  module-level `PROVIDERS` registry.
- A load failure raises `ProviderError`.

### ProviderBase
Location: `notify/providers/base.py`
- Abstract base for **all** providers. Key class attributes:
  - `provider: str` — registry name (must match the package directory).
  - `provider_type: ProviderType` — `NOTIFY | SMS | EMAIL | PUSH | IM`.
  - `blocking: bool | str` — `True`, `'asyncio'`, or `'executor'`; decides how
    `send()` dispatches work (native await, event loop, or thread executor).
- Async context manager: `async with Notify("telegram", ...) as t: ...`
  (`__aenter__` → `connect()`, `__aexit__` → `close()`).
- Lifecycle hooks a provider implements: `connect()`, `close()`,
  `_prepare_()`, `_render_()` / `_render_sync_()`, `_send_()`, `__sent__()`.
- Public entry point is `send()` — subclasses override `_send_()`, not `send()`.

### Provider families
Location: `notify/providers/base.py`
- `ProviderMessaging` — SMS-style services (`ProviderType.SMS`).
- `ProviderIM` — instant messengers (`ProviderType.IM`).
- `ProviderPush` — push notifications (`ProviderType.PUSH`).
Email providers extend `ProviderBase` (or the shared mail helpers) directly.

### Provider layout
Location: `notify/providers/<name>/`
Each provider is a package: `__init__.py` re-exports the class defined in
`<name>.py`. Shared email plumbing lives at the `notify/providers/` top level:
- `mail.py` — common SMTP/IMAP-flavoured base.
- `message.py` — message assembly.
- `_mime_utils.py` — MIME/UTF-8 encoding helpers (see NAV-8390).

### Models
Location: `notify/models.py`
Pydantic models for the domain: `Account`, `Actor`, `Chat`, `Channel`,
`Message`, `Attachment`, `BlockMessage`, `MailMessage`, `MailAttachment`, and
the Teams card family (`TeamsCard`, `TeamsSection`, `TeamsAction`, …).
New data structures MUST be Pydantic models, never bare dicts.

### TemplateParser
Location: `notify/templates.py`
Jinja2 wrapper (`enable_async=True`) used to render message bodies from the
template directory configured via `TEMPLATE_DIR` in `notify/conf.py`.

### Notify Server
Location: `notify/server/`
Optional Redis-backed notification service:
- `server.py` — the worker/service process (Redis Streams + pub/sub).
- `queue.py` — `QueueManager`.
- `client.py` — client-side API for enqueueing notifications.
- `wrapper.py` — provider wrapper used by workers.

### Exceptions
Location: `notify/exceptions.pyx` (Cython)
`NotifyException`, `ProviderError`, `NotSupported`, … Compiled — after editing
the `.pyx` you must rebuild the extension.

---

## Configuration
Location: `notify/conf.py`
Configuration is read via **navconfig** (env vars + `env/` files). Never
hardcode credentials or read `os.environ` directly in a provider — add the key
to `conf.py` and import it.

---

## Cython Extensions
`notify/exceptions.pyx` and `notify/types/typedefs.pyx` are Cython modules.
- Follow `.claude/rules/cython-development.md` (prefer `cimport`, `cdef`,
  static typing).
- Rebuild after edits: `python setup.py build_ext --inplace`.
- Generated `.c` sources are NOT tracked in git.

---

## Conventions
- **Async-first.** No blocking I/O inside coroutines; if a third-party SDK is
  sync-only, route it through `blocking = 'executor'`.
- **Type hints + Google-style docstrings** on every public function/class.
- **Logging** via navconfig's logger (`self.logger`), never `print`.
- **Tests** live in `tests/`; run `pytest` after any logic change.
  `pytest.ini` sets `asyncio_mode = auto` and defines the `integration`,
  `live` and `real_llm` markers for tests that need external services.

---

## Adding a New Provider — checklist
1. Create `notify/providers/<name>/` with `__init__.py` + `<name>.py`.
2. Subclass the right base (`ProviderBase` / `ProviderMessaging` /
   `ProviderIM` / `ProviderPush`) and set `provider`, `provider_type`,
   `blocking`.
3. Implement `connect()`, `close()`, `_send_()` (and `_prepare_()` /
   `_render_()` when the provider needs templating).
4. Add credentials/settings to `notify/conf.py` via navconfig.
5. Add an offline unit test in `tests/` (mock the transport) plus, when
   relevant, an `@pytest.mark.integration` live test.
6. Document usage in `docs/` and `README.md`.

---

## Key References
- SDD workflow: `docs/sdd/WORKFLOW.md`, `docs/sdd/GUIDE.md`,
  `docs/sdd/PLATFORM.md`
- Rules: `.claude/rules/` (python, cython, rust/PyO3, worktrees)
- Skills: `.agent/skills/`
- Workflows: `.agent/workflows/`
