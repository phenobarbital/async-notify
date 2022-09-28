from navconfig import config


# Amazon AWS
AWS_EMAIL_USER = config.get('aws_email_user')
AWS_EMAIL_PASSWORD = config.get('aws_email_password')
AWS_EMAIL_HOST = config.get(
    'aws_email_host', fallback='email-smtp.us-east-1.amazonaws.com'
)
AWS_EMAIL_PORT = config.get('aws_email_port', fallback=587)
AWS_EMAIL_ACCOUNT = config.get('aws_email_account')
