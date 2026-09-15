---
trigger: always_on
---
# async-notify codebase conventions

Binding for every file you touch in this repository — Python and Cython alike.
If a task file and this document disagree, STOP and report — never pick one silently.

## Stack
- Asyncio library: every transport is reached through a provider; I/O paths are `async def` and never block the event loop (no `time.sleep`, no sync HTTP/SMTP/DB calls in coroutines).
- Sync-only third-party SDKs run through `blocking = 'executor'` on the provider (see `ProviderBase.send()` in `notify/providers/base.py`), never called inline from a coroutine.
- Providers subclass `ProviderBase` / `ProviderMessaging` / `ProviderIM` / `ProviderPush` (`notify/providers/base.py`), declare `provider`, `provider_type` and `blocking`, and implement `_send_()` — never override `send()`.
- User-facing code instantiates providers through the `Notify` factory (`notify/notify.py`), never by importing a concrete provider.
- Configuration and credentials come from `notify/conf.py` (navconfig) — never `os.environ` inside a provider.
- Domain models live in `notify/models.py` and follow its existing declarative model pattern (`from datamodel import BaseModel`); new data structures are models, never bare dicts. Do not introduce a second model library.
- Message bodies are rendered through `TemplateParser` (`notify/templates.py`, Jinja2 with `enable_async=True`).
- Logging is `self.logger`, never `print`.

## Forbidden — and what to use instead
| Never import / use | Use instead |
|---|---|
| `requests`, `httpx` in new code | `aiohttp` (or the transport's own async client, e.g. `aiosmtplib`, `aiobotocore`) |
| a blocking SDK call inside `async def` | `blocking = 'executor'` on the provider |
| `os.environ[...]` in a provider | a setting in `notify/conf.py` |
| direct `from notify.providers.<name> import ...` in user-facing code | `Notify("<name>", ...)` |
| `print(...)` | `self.logger.<level>(...)` |
| `pip`, `poetry`, `requirements.txt` | `uv add` / `uv pip`, dependencies in `pyproject.toml` |

## Repository layout
- Flat layout: the import package `notify/` sits at the repo root (distribution `async-notify`). There is no `packages/` workspace.
- Providers: `notify/providers/<name>/` with `__init__.py` re-exporting the class from `<name>.py`. Shared email plumbing: `notify/providers/mail.py`, `message.py`, `_mime_utils.py`.
- Optional Redis-backed service: `notify/server/`.
- Tests: `tests/` (`pytest.ini` sets `asyncio_mode = auto`; `integration`, `live` and `real_llm` markers gate tests that need external services). SDD tooling tests: `tests/sdd_scripts/`.

## Tooling
- `source .venv/bin/activate` first; then `uv add` / `uv pip`, `pytest`. Never run `python`/`uv`/`pip` outside the venv.
- `black` formats at 120 columns; `flake8` (`.flake8`, max-line-length 120) and `pylint` (`.pylintrc`) lint.
- Run your task's tests before committing; add an offline unit test (mock the transport) for every provider change.

## Python
- Google-style docstrings and strict type hints on every function and class.
- `snake_case` functions/variables, `PascalCase` classes, 120-column lines; PEP 8 otherwise.
- Context managers for resources (`async with Notify(...) as provider:`); `await` for I/O.
- Secrets come only from environment variables via navconfig — never in code or committed files.
- Complete, working files: no `TODO`, no stubs, no "existing code here" placeholders.
- Minimal, focused diffs: touch only the files your task lists; never refactor outside scope.

## Cython (`notify/exceptions.pyx`, `notify/types/typedefs.pyx`)
- Prefer `cimport` over `import` for anything exposed via a `.pxd`; use Cython syntax (`cdef`, `cpdef`) and static typing rather than pure-Python-mode decorators.
- Keep the `.pxd` in sync with the `.pyx` so other modules can `cimport` it.
- Rebuild after every edit: `python setup.py build_ext --inplace`. Generated `.c` sources and `.so` files are not tracked.
