from navconfig import config


# email:
EMAIL_SMTP_USERNAME = config.get('stmp_host_user')
EMAIL_SMTP_PASSWORD = config.get('stmp_host_password')
EMAIL_SMTP_PORT = config.get('smtp_port', fallback=587)
EMAIL_SMTP_HOST = config.get('stmp_host')
