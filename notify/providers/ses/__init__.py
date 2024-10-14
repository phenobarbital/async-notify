"""
Amazon SES

using Boto3 to send emails through Amazon SES.
"""
from .ses import Ses

__all__ = ("Ses",)
