from unittest.mock import AsyncMock, patch
import pytest
from notify.models import Actor
from notify.providers.ses import Ses
from notify.tests.base import BaseTestCase


# Mock AWS credentials and email information for testing
AWS_ACCESS_KEY = "mock_access_key"
AWS_SECRET_KEY = "mock_secret_key"
AWS_REGION = "mock_region"
SENDER_EMAIL = "sender@example.com"
RECIPIENT_EMAIL = "recipient@example.com"


class TestSesComponent(BaseTestCase):
    component_class = Ses
    component_params = {
        'aws_access_key_id': AWS_ACCESS_KEY,
        'aws_secret_access_key': AWS_SECRET_KEY,
        'aws_region_name': AWS_REGION,
        'sender_email': SENDER_EMAIL,
        'use_aws_template': False
    }

    def test_required_variables_on_connect(self):
        required_variables = ['aws_access_key_id', 'aws_secret_access_key', 'aws_region_name']
        for var in required_variables:
            assert getattr(self.component, var) is not None

    @pytest.mark.asyncio
    async def test_send_email(self):
        recipient = Actor(account={"address": RECIPIENT_EMAIL})

        # Mock the client and its method
        mock_client = AsyncMock()
        # Set the async return value correctly using awaitable return value
        mock_client.__aenter__.return_value.send_raw_email.return_value = {'MessageId': 'mock_message_id'}

        # Patch the 'create_client' to return the mock client
        with patch.object(self.component.session, 'create_client', return_value=mock_client):
            # Send the email
            response = await self.component.send(
                recipient=[recipient],
                message="Test email body",
                subject="Test Subject"
            )

            mock_client.__aenter__.return_value.send_raw_email.assert_called_once()
            assert response[0]['MessageId'] == 'mock_message_id'

    @pytest.mark.asyncio
    async def test_send_templated_email(self):
        # Set the use_aws_template flag to True
        self.component.use_aws_template = True
        recipient = Actor(account={"address": RECIPIENT_EMAIL})

        # Mock the client and its method
        mock_client = AsyncMock()
        # Set the async return value correctly using awaitable return value
        mock_client.__aenter__.return_value.send_templated_email.return_value = {'MessageId': 'mock_message_id'}

        # Patch the 'create_client' to return the mock client
        with patch.object(self.component.session, 'create_client', return_value=mock_client):
            # Send the templated email
            response = await self.component.send(
                recipient=[recipient],
                message=None,
                subject=None,
                template_name="AdvancedTemplate",
                template_data='{"name": "John", "article_titles": "Python for Beginners, AWS SES Tips"}'
            )
            mock_client.__aenter__.return_value.send_templated_email.assert_called_once_with(
                Source=SENDER_EMAIL,
                Destination={'ToAddresses': [RECIPIENT_EMAIL]},
                Template="AdvancedTemplate",
                TemplateData='{"name": "John", "article_titles": "Python for Beginners, AWS SES Tips"}'
            )
            assert response['MessageId'] == 'mock_message_id'
