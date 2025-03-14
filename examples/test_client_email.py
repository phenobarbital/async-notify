import asyncio
from notify.server import NotifyClient
from notify.conf import NOTIFY_WORKER_STREAM, NOTIFY_REDIS, NOTIFY_DEFAULT_PORT

jesus = {
    "name": "Jesus Lara",
    "account": {
        "address": "jesuslarag@gmail.com",
    }
}
jlara = {
    "name": "Jesus Lara",
    "account": {
        "address": "jlara@trocglobal.com",
    }
}
victor = {
    "name": "Victor Inojosa",
    "account": {
        "address": "vinojosa@trocglobal.com",
    }
}
javier = {
    "name": "Javier Leon",
    "account": {
        "address": "jleon@trocglobal.com",
    }
}
juan = {
    "name": "Juan Rodriguez R.",
    "account": {
        "address": "jfrruffato@trocglobal.com",
    }
}
oslan = {
    "name": "Oslan Villalobos",
    "account": {
        "address": "ovillalobos@trocglobal.com",
    }
}
recipients = [jesus, jlara, victor, javier, juan, oslan]

async def main():
    # Sample message
    msg = {
        "provider": "ses",
        "subject": 'Este es un correo de pruebas de Polestar Pilates!',
        "event_name": 'Si ha recibido este email, el sistema de envío de correos funciona correctamente.',
        "event_address": 'Polestar Pilates',
        "template": 'email_applied.html'
    }
    # Create a NotifyClient instance
    async with NotifyClient() as client:
        for recipient in recipients:
            msg['recipient'] = [recipient]
            # Stream but using Wrapper:
            await client.stream(
                msg,
                stream=NOTIFY_WORKER_STREAM,
                use_wrapper=True
            )

# Run the example
if __name__ == "__main__":
    asyncio.run(main())
