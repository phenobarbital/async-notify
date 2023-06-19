from typing import Optional
from collections.abc import Callable
from unittest.mock import AsyncMock, patch
import pytest


class BaseTestCase:
    component_class: Optional[Callable] = None
    component_params = {}

    @pytest.fixture(autouse=True)
    async def setup_component(self):
        self.component = self.component_class(**self.component_params)
        await self.component.connect()
        yield
        await self.component.close()

    @pytest.mark.asyncio
    async def test_context_methods(self):
        with patch.object(self.component, 'connect', new_callable=AsyncMock) as mock_connect, \
             patch.object(self.component, 'close', new_callable=AsyncMock) as mock_close:
            async with self.component:
                mock_connect.assert_called_once()
            mock_close.assert_called_once()

    def test_required_variables_on_connect(self):
        required_variables = ['client_id', 'client_secret', 'tenant_id']
        for var in required_variables:
            assert getattr(self.component, var) is not None

    @pytest.mark.asyncio
    async def test_authenticate(self):
        async with self.component_class(**self.component_params) as component:
            if hasattr(component, 'authenticate'):
                assert component.authenticate is True
