from typing import Optional, Union, Any
from collections.abc import Callable
import asyncio
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import aiobotocore
from botocore.exceptions import ClientError
from navconfig.logging import logging
from notify.providers.mail import ProviderEmail
from notify.exceptions import NotifyAuthError
from notify.models import Actor
from notify.conf import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_REGION_NAME,
    AWS_SENDER_EMAIL
)

logging.getLogger("aiobotocore").setLevel(logging.CRITICAL)


class Ses(ProviderEmail):
    """Amazon SES-based Email Provider"""

    provider = "amazon_ses"
    blocking: str = "asyncio"

    def __init__(
        self,
        *args,
        aws_access_key_id: str = None,
        aws_secret_access_key: str = None,
        aws_region_name: str = None,
        sender_email: str = None,
        use_aws_template: bool = False,
        template_name: Optional[str] = None,
        **kwargs,
    ):
        self.authenticate: bool = False
        self.session: Callable = None
        self.client: Callable = None
        self.use_aws_template: bool = use_aws_template
        self.template_name: Optional[str] = template_name
        super(Ses, self).__init__(*args, **kwargs)

        self.aws_access_key_id = aws_access_key_id or AWS_ACCESS_KEY_ID
        self.aws_secret_access_key = aws_secret_access_key or AWS_SECRET_ACCESS_KEY
        self.aws_region_name = aws_region_name or AWS_REGION_NAME
        self.sender_email = sender_email or AWS_SENDER_EMAIL

        if not all(
            [
                self.aws_access_key_id,
                self.aws_secret_access_key,
                self.aws_region_name,
                self.sender_email,
            ]
        ):
            raise RuntimeWarning(
                f"To send emails via {self.name}, you need to configure "
                "AWS credentials, region, and sender email. \n"
                "Either send them as function arguments or set up "
                "environment variables as `AWS_ACCESS_KEY_ID`, "
                "`AWS_SECRET_ACCESS_KEY`, `AWS_REGION_NAME`, and "
                "`AWS_SENDER_EMAIL`."
            )

    async def connect(self, **kwargs):
        """Connect to Amazon SES using aiobotocore."""
        self.session = aiobotocore.get_session()
        try:
            self.client = self.session.create_client(
                "ses",
                region_name=self.aws_region_name,
                aws_secret_access_key=self.aws_secret_access_key,
                aws_access_key_id=self.aws_access_key_id,
            )
            self.authenticate = True
            return self.client
        except Exception as e:
            self.logger.error(f"Error during authentication: {e}")
            raise NotifyAuthError(
                f"Unable to authenticate with Amazon SES: {e}"
            )

    async def close(self):
        """Close the connection."""
        if self.client:
            await self.client.close()

    async def _render_(self, to: Actor, message: str = None, subject: str = None, **kwargs):
        """Create the email message."""
        if self._template:
            templateargs = {
                "recipient": to,
                "username": to,
                "message": message,
                "content": message,
                **kwargs,
            }
            msg = await self._template.render_async(**templateargs)
        else:
            try:
                msg = kwargs["body"]
            except KeyError:
                msg = message

        email_msg = MIMEMultipart("alternative")
        email_msg["Subject"] = subject
        email_msg["From"] = self.sender_email
        email_msg["To"] = to.account.address
        email_msg.attach(MIMEText(message, "plain"))
        email_msg.attach(MIMEText(msg, "html"))

        return email_msg

    async def _send_(self, to: Actor, message: str, subject: str, **kwargs):
        """Send the email message to the recipient."""
        if self.use_aws_template:
            # Use AWS SES templates to send the email
            try:
                response = await self.client.send_templated_email(
                    Source=self.sender_email,
                    Destination={
                        'ToAddresses': [to.account.address],
                    },
                    Template=self.template_name,
                    TemplateData=kwargs,
                )
                return response
            except ClientError as e:
                self.logger.exception(e, stack_info=True)
                raise RuntimeError(f"{e}") from e
        else:
            try:
                message = await self._render_(to, message, subject, **kwargs)
            except (TypeError, ValueError) as exc:
                self.logger.error(exc)
                return False

            try:
                response = await self.client.send_raw_email(
                    Source=self.sender_email,
                    Destinations=[to.account.address],
                    RawMessage={"Data": message.as_string()},
                )
                return response
            except ClientError as exc:
                self.logger.exception(exc, stack_info=True)
                raise RuntimeError(f"{exc}") from exc

    async def send(
        self,
        recipient: list[Actor] = None,
        message: Union[str, Any] = None,
        subject: str = None,
        **kwargs,
    ):
        """
        send.

        Send Email Messages using Amazon SES Templates.
        """
        # template (or message) for preparation
        message = await self._prepare_(
            recipient=recipient,
            message=message,
            **kwargs
        )
        results = []
        recipients = [recipient] if not isinstance(recipient, list) else recipient
        if self.use_aws_template:
            # Use AWS SES templates to send the email
            try:
                results = await self.client.send_templated_email(
                    Source=self.sender_email,
                    Destination={
                        'ToAddresses': recipients,
                    },
                    Template=self.template_name,
                    TemplateData=kwargs,
                )
            except ClientError as e:
                self.logger.exception(e, stack_info=True)
                raise RuntimeError(f"{e}") from e
        else:
            # Using basic Asyncio _send_ method
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.get_event_loop()
            # asyncio:
            tasks = [self._send_(to, message, subject=subject, **kwargs) for to in recipients]
            # Using asyncio.as_completed to get results as they become available
            for to, future in zip(recipients, asyncio.as_completed(tasks)):
                result = None
                try:
                    result = await future
                    results.append(result)
                except Exception as e:
                    self.logger.exception(
                        f'Send for recipient {to} raised an exception: {e}',
                        stack_info=True
                    )
                try:
                    await self.__sent__(to, message, result, loop=loop, **kwargs)
                except Exception as e:
                    self.logger.exception(
                        f'Send for recipient {to} raised an exception: {e}',
                        stack_info=True
                    )
        return results
