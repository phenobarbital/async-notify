import asyncio
from navconfig import config
from notify.providers.ses import Ses
from notify.models import Actor
from notify.utils import Msg


jesus = {
    "name": "Jesus Lara",
    "account": {
        "address": "jesuslarag@gmail.com",
        "number": "+34692817379"
    }
}
carlos = {
    "name": "Carlos Montes",
    "account": {
        "address": "cmontes@trocglobal.com",
    }
}
javier = {
    "name": "Javier Leon",
    "account": {
        "address": "jleon@trocglobal.com",
    }
}
eduardo = {
    "name": "Eduardo Santaella",
    "account": {
        "address": "esantaella@trocglobal.com",
    }
}

recipients = [
    Actor(**jesus),
    # Actor(**eduardo),
    # Actor(**javier)
]

Msg('=== Test EMAIL Using SES === ')

credentials = {
    "aws_access_key_id": config.get('AWS_ACCESS_KEY_ID'),
    "aws_secret_access_key": config.get('AWS_SECRET_ACCESS_KEY'),
    "aws_region_name": config.get('AWS_REGION_NAME'),
    "sender_email": "navigatoralerts@trocglobal.com" # config.get('AWS_SENDER_EMAIL')
}

async def send_email():
    mail = Ses(
        **credentials
    )
    print(f'Sending email... {credentials}')
    async with mail as m:
        await m.send(
            recipient=recipients,
            subject='Este es un correo de pruebas de Polestar Pilates!',
            event_name='Si ha recibido este email, el sistema de envío de correos funciona correctamente.',
            event_address='Polestar Pilates',
            template='email_applied.html'
        )


if __name__ == '__main__':
    Msg('=== Test EMAIL Using AWS SES === ')
    asyncio.run(send_email())
