---
id: F008
query_id: Q006
type: read
intent: Check whether provider modules guard third-party imports and what a missing dep looks like
executed_at: 2026-09-29T16:00:00Z
parent_id: null
depth: 0
---

# F008 — A missing optional SDK is reported as "No Provider X was Found"

## Summary

No provider module guards its third-party import. Grep over
`notify/providers`, `notify/server` and `notify/utils` finds only three
`except ImportError` sites, none of them a provider top-level guard. Executed
probe: blocked `aiogram` on `sys.meta_path` and called `Notify("telegram", …)`.
The result conflates *provider does not exist* with *provider's optional
dependency is not installed*, never names the extra to install, and logs at
`CRITICAL` for what is a user install problem.

## Citations

- path: `notify/notify.py`
  lines: 79-86
  symbol: `LoadProvider` except branch
  excerpt: |
        except ImportError:
            try:
                obj = __import__(classpath, fromlist=[provider])
                return obj
            except ImportError as exc:
                raise NotifyException(
                    f"Error: No Provider {provider} was Found: {exc}"
                ) from exc

- path: `notify/notify.py`
  lines: 42-48
  symbol: `Notify.__new__` except branch
  excerpt: |
        except Exception as ex:
            logger.critical(f"Cannot Load provider {provider}: {ex}")
            raise ProviderError(
                message=f"Cannot Load provider {provider}: {ex}"
            ) from ex

- path: `notify/utils/uv.py`
  lines: 14
  symbol: `install_uvloop` guard
  excerpt: |
        except ImportError:

- path: `notify/providers/telegram/Telegram.py`
  lines: 344
  symbol: in-method guard
  excerpt: |
            except ImportError:

## Notes

**Executed probe output** (aiogram blocked via a `sys.meta_path` finder):

    [CRITICAL] navconfig.logging(notify.py:43) :: Cannot Load provider telegram:
      Error: No Provider telegram was Found: No module named 'aiogram'
    TYPE: ProviderError
    MSG : Cannot Load provider telegram: Error: No Provider telegram was Found:
          No module named 'aiogram'
      CAUSE: NotifyException  Error: No Provider telegram was Found: ...
      CAUSE: ImportError      No module named 'aiogram'

Two latent defects in the same block: (a) the `except ImportError` fallback
re-runs `__import__` on the *same* `classpath` that just failed, so it can only
succeed in pathological cases; (b) when it does succeed it returns the **module**,
not `getattr(module, provider.capitalize())` — a different type from the happy
path.

**In-tree precedent for the fix.** `Telegram.py:343-347` already does exactly
what `LoadProvider` should do — defer the import and name the extra:

    try:
        from moviepy import VideoFileClip
    except ImportError:
        raise ... (
            "moviepy is required to convert videos to mp4. "
            "Install it with `pip install async-notify[telegram]` or "
            "`pip install moviepy==2.2.1`"
        )

This is the pattern to generalise into `LoadProvider`, plus `install_uvloop`'s
guard in `notify/utils/uv.py:14`.
