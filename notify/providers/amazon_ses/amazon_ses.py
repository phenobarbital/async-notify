"""
Amazon SES.

"""

from notify.providers.abstract import ProviderBase, ProviderType


class Amazon_ses(ProviderBase):
    """
    amazon_ses.
       Send emails using boto3
    """
    provider = 'ses'
    provider_type = ProviderType.EMAIL
