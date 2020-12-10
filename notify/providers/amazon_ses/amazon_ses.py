"""
Amazon SES.

"""
from notify import settings
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from notify.providers import ProviderBase
import boto3
from botocore.exceptions import ClientError


class Amazon_ses(ProviderBase):
    """
    amazon_ses.
       Send emails using boto3
    """
    pass
