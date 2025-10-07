Examples
========

This page contains detailed examples of using async-notify in various scenarios.

Basic Usage
---------

Simple Email
~~~~~~~~~~

.. code-block:: python

    from notify import Notify

    async def send_email():
        # Create email provider
        email = Notify(
            "email",
            username="user@example.com",
            password="secret",
            hostname="smtp.example.com",
            port=587
        )
        
        # Send email
        await email.send(
            recipient=["user@example.com"],
            subject="Test Email",
            message="Hello from async-notify!"
        )

HTML Email with Template
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from notify import Notify
    from pathlib import Path

    async def send_template_email():
        email = Notify(
            "email",
            username="user@example.com",
            password="secret"
        )
        
        # Send using template
        await email.send(
            recipient=["user@example.com"],
            subject="Welcome",
            template="welcome.html",
            template_data={
                "name": "John",
                "company": "Acme Inc"
            }
        )

Instant Messaging
--------------

Telegram Bot
~~~~~~~~~~

.. code-block:: python

    from notify import Notify
    from notify.models import Chat

    async def send_telegram():
        # Create Telegram provider
        telegram = Notify(
            "telegram",
            bot_token="YOUR_BOT_TOKEN"
        )
        
        # Send to chat
        chat = Chat(
            chat_id="CHAT_ID",
            chat_name="My Chat"
        )
        
        # Send text
        await telegram.send(
            recipient=chat,
            message="Hello from async-notify!"
        )
        
        # Send photo
        await telegram.send_photo(
            "path/to/photo.jpg",
            caption="Check out this photo!"
        )

Microsoft Teams
~~~~~~~~~~~~

.. code-block:: python

    from notify import Notify
    from notify.models import TeamsChannel, TeamsCard

    async def send_teams():
        # Create Teams provider
        teams = Notify(
            "teams",
            tenant_id="TENANT_ID",
            client_id="CLIENT_ID",
            client_secret="CLIENT_SECRET"
        )
        
        # Create channel
        channel = TeamsChannel(
            channel_id="CHANNEL_ID",
            team_id="TEAM_ID",
            name="General"
        )
        
        # Create card
        card = TeamsCard(
            title="Meeting Reminder",
            summary="Team meeting at 2 PM",
            sections=[{
                "activityTitle": "Weekly Team Meeting",
                "activitySubtitle": "2:00 PM - 3:00 PM",
                "facts": [
                    {"name": "Location", "value": "Conference Room A"},
                    {"name": "Organizer", "value": "John Smith"}
                ]
            }]
        )
        
        # Send card
        await teams.send(
            recipient=channel,
            message=card
        )

SMS and Voice
----------

Twilio SMS
~~~~~~~~

.. code-block:: python

    from notify import Notify
    from notify.models import Actor, Account

    async def send_sms():
        # Create Twilio provider
        twilio = Notify(
            "twilio",
            account_sid="YOUR_SID",
            auth_token="YOUR_TOKEN",
            from_number="+1234567890"
        )
        
        # Create recipient
        recipient = Actor(
            name="John Smith",
            account=Account(
                provider="twilio",
                number="+1987654321"
            )
        )
        
        # Send SMS
        await twilio.send(
            recipient=recipient,
            message="Your verification code is: 123456"
        )

Server Components
--------------

NotifyWorker Server
~~~~~~~~~~~~~~~~

.. code-block:: python

    from notify.server import NotifyWorker
    import asyncio

    async def run_server():
        # Create worker
        worker = NotifyWorker(
            host="0.0.0.0",
            port=8991,
            notify_empty_stream=True
        )
        
        # Start server
        await worker.start()

NotifyClient Usage
~~~~~~~~~~~~~~~

.. code-block:: python

    from notify.server import NotifyClient
    from notify.models import Actor, Account

    async def use_client():
        # Create client
        client = NotifyClient(
            redis_url="redis://localhost:6379/0",
            tcp_host="localhost",
            tcp_port=8991
        )
        
        # Connect
        async with client:
            # Send via TCP
            await client.send({
                "provider": "email",
                "recipient": ["user@example.com"],
                "subject": "Test",
                "message": "Hello!"
            })
            
            # Publish to Redis channel
            await client.publish(
                message={"type": "notification", "data": "..."},
                channel="notifications"
            )
            
            # Add to Redis stream
            await client.stream(
                message={"type": "task", "data": "..."},
                stream="notification_stream"
            )

Advanced Features
--------------

Custom Templates
~~~~~~~~~~~~~

.. code-block:: python

    from notify import Notify
    from pathlib import Path

    # Create template directory
    template_dir = Path("templates")
    template_dir.mkdir(exist_ok=True)

    # Create template file
    template = """
    <html>
        <body>
            <h1>Welcome {{ name }}!</h1>
            <p>Thanks for joining {{ company }}.</p>
            {% if is_admin %}
            <p>You have admin access.</p>
            {% endif %}
        </body>
    </html>
    """

    with open(template_dir / "welcome.html", "w") as f:
        f.write(template)

    async def send_custom_template():
        email = Notify(
            "email",
            username="user@example.com",
            password="secret",
            template_dir=template_dir
        )
        
        await email.send(
            recipient=["new.user@example.com"],
            subject="Welcome!",
            template="welcome.html",
            template_data={
                "name": "John Smith",
                "company": "Acme Inc",
                "is_admin": True
            }
        )

Error Handling
~~~~~~~~~~~

.. code-block:: python

    from notify import Notify
    from notify.exceptions import ProviderError, NotifyException

    async def handle_errors():
        try:
            email = Notify(
                "email",
                username="user@example.com",
                password="wrong_password"
            )
            
            await email.send(
                recipient=["user@example.com"],
                subject="Test",
                message="Hello!"
            )
            
        except ProviderError as e:
            print(f"Provider error: {e}")
            # Handle provider-specific errors
            
        except NotifyException as e:
            print(f"General error: {e}")
            # Handle general errors