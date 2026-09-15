"""Optional uvloop integration."""

import asyncio


def install_uvloop() -> bool:
    """Install uvloop when it is available on the current platform.

    Returns:
        ``True`` when uvloop was installed, otherwise ``False``.
    """
    try:
        import uvloop  # pylint: disable=import-outside-toplevel
    except ImportError:
        return False

    try:
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        uvloop.install()
    except (NotImplementedError, RuntimeError):
        return False
    return True
