"""Offline tests for `Notify("outlook", ...)` factory integration (FEAT-004, M7/M11).

Previously based on `notify.tests.base.BaseTestCase`, whose autouse fixture
drives a real `connect()`/`close()` and expects legacy `authenticate`/token-file
attributes that no longer apply to the Graph-based provider (spec §7 open
question, resolved here: plain fixtures, not `BaseTestCase`). `connect()`
itself is still safe to call for real — it is network-free (FEAT-004,
TASK-26) — these tests just no longer assume the legacy REST lifecycle.

Deeper Outlook-specific lifecycle/queueing coverage lives in
`tests/test_outlook1.py`; this file focuses on the `Notify` factory path.
"""
import pytest

from notify import Notify
from notify.providers.office365.office365 import Office365
from notify.providers.outlook import Outlook


COMPONENT_PARAMS = {
    "client_id": "test_client_id",
    "client_secret": "test_client_secret",
    "tenant_id": "test_tenant_id",
}


async def test_notify_factory_loads_outlook():
    async with Notify("outlook", **COMPONENT_PARAMS) as instance:
        assert isinstance(instance, Outlook)
        assert isinstance(instance, Office365)
        assert instance.provider == "outlook"


async def test_notify_factory_outlook_connect_close_no_network():
    instance = Notify("outlook", **COMPONENT_PARAMS)
    assert instance._graph is None
    await instance.connect()
    assert instance._graph is not None
    await instance.close()
    assert instance._graph is None


async def test_required_variables_on_connect():
    async with Notify("outlook", **COMPONENT_PARAMS) as instance:
        for var in ("client_id", "client_secret", "tenant_id"):
            assert getattr(instance, var) is not None


async def test_authenticate_attribute_not_present():
    # The legacy REST-client `authenticate` flag no longer exists; nothing in
    # this feature's provider should reintroduce it.
    async with Notify("outlook", **COMPONENT_PARAMS) as instance:
        assert not hasattr(instance, "authenticate")
