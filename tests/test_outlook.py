from notify.tests import BaseTestCase
from notify.providers.outlook import Outlook


class TestOutlook(BaseTestCase):
    component_class = Outlook
    component_params = {
        "client_id": "test_client_id",
        "client_secret": "test_client_secret",
        "tenant_id": "test_tenant_id",
    }
