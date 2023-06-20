from unittest.mock import AsyncMock, patch
import pytest
from notify.providers.outlook import Outlook

@pytest.fixture
def outlook():
    return Outlook(
        client_id='test_client_id',
        client_secret='test_client_secret',
        tenant_id='test_tenant_id'
    )

@pytest.mark.asyncio
async def test_context_methods(outlook):
    with patch.object(outlook, 'connect', new_callable=AsyncMock) as mock_connect, \
         patch.object(outlook, 'close', new_callable=AsyncMock) as mock_close:
        async with outlook:
            mock_connect.assert_called_once()
        mock_close.assert_called_once()

@pytest.mark.asyncio
async def test_connect(outlook):
    with patch.object(outlook, 'acquire_token', return_value='test_token'):
        await outlook.connect()
        assert outlook.client is not None

# @pytest.mark.asyncio
# async def test_close(outlook):
#     with patch.object(outlook, 'client', autospec=True) as mock_client:
#         await outlook.close()
#         mock_client.close.assert_called_once()

def test_required_variables_on_connect(outlook):
    required_variables = ['client_id', 'client_secret', 'tenant_id']
    for var in required_variables:
        assert getattr(outlook, var) is not None
