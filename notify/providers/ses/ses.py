from typing import Optional, Union, Any
from collections.abc import Callable
import asyncio
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from aiobotocore.session import get_session
from botocore.exceptions import ClientError
from navconfig.logging import logging
from notify.providers.mail import ProviderEmail
from notify.models import Actor
from notify.conf import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_REGION_NAME,
    AWS_SENDER_EMAIL
)

logging.getLogger("aiobotocore").setLevel(logging.CRITICAL)
logging.getLogger("botocore").setLevel(logging.INFO)


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
        """Create a Session to Amazon SES using aiobotocore."""
        self.session = get_session()
        self.authenticate = True

    async def close(self):
        """Close the connection."""
        self.client = None
        self.session = None
        self.authenticate = False

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
            content = await self._template.render_async(**templateargs)
        else:
            try:
                content = kwargs["body"]
            except KeyError:
                content = message
        email_msg = MIMEMultipart("alternative")
        email_msg["Subject"] = subject
        email_msg["From"] = self.sender_email
        email_msg["To"] = to.account.address
        email_msg.attach(MIMEText(content, "plain"))
        email_msg.attach(MIMEText(content, "html"))
        return email_msg

    async def _send_(
        self,
        to: Actor,
        message: str,
        subject: str,
        client: Optional[Callable] = None,
        **kwargs
    ):
        """Send the email message to the recipient."""
        if self.use_aws_template:
            # Use AWS SES templates to send the email
            try:
                response = await client.send_templated_email(
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
                response = await client.send_raw_email(
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
        if self.use_aws_template:
            # Use AWS SES templates to send the email
            recipients = [recipient.account.address for recipient in recipient]
            template_name = kwargs.pop('template_name', self.template_name)
            template_data = kwargs.pop('template_data', {})
            if not template_data:
                template_data = {}
            try:
                async with self.session.create_client(
                    "ses",
                    region_name=self.aws_region_name,
                    aws_secret_access_key=self.aws_secret_access_key,
                    aws_access_key_id=self.aws_access_key_id,
                ) as client:
                    results = await client.send_templated_email(
                        Source=self.sender_email,
                        Destination={
                            'ToAddresses': recipients,
                        },
                        Template=template_name,
                        TemplateData=template_data,
                    )
            except ClientError as e:
                self.logger.exception(e, stack_info=True)
                raise RuntimeError(f"{e}") from e
        else:
            # Using basic Asyncio _send_ method
            recipients = [recipient] if not isinstance(recipient, list) else recipient
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.get_event_loop()
            # asyncio:
            async with self.session.create_client(
                    "ses",
                    region_name=self.aws_region_name,
                    aws_secret_access_key=self.aws_secret_access_key,
                    aws_access_key_id=self.aws_access_key_id,
            ) as client:
                tasks = [
                    self._send_(
                        to, message, subject=subject, client=client, **kwargs
                    ) for to in recipients
                ]
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

    async def create_template(self, template_name: str, subject_part: str, html_part: str, text_part: str):
        """
        Create a new SES email template using SES V2 API.

        :param template_name: The name of the email template to create.
        :param subject_part: The subject of the email template.
        :param html_part: The HTML content of the email template.
        :param text_part: The text content of the email template.
        """
        template = {
            "Template": {
                "TemplateName": template_name,
                "SubjectPart": subject_part,
                "HtmlPart": html_part,
                "TextPart": text_part
            }
        }

        try:
            async with self.session.create_client(
                "sesv2",  # Use the SES v2 API endpoint
                region_name=self.aws_region_name,
                aws_secret_access_key=self.aws_secret_access_key,
                aws_access_key_id=self.aws_access_key_id,
            ) as client:
                response = await client.invoke_endpoint(
                    "CreateEmailTemplate",
                    Template=template
                )
                self.logger.debug(
                    f"Template created successfully: {response}"
                )
                return response
        except ClientError as exc:
            self.logger.exception(
                f"Error creating SES email template: {exc}"
            )
            raise RuntimeError(
                f"Failed to create SES email template: {exc}"
            ) from exc
