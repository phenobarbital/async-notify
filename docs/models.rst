Data Models
===========

async-notify uses several data models to represent different aspects of the notification system.

Actor Models
----------

The Actor model represents both senders and recipients in the notification system.

Account
~~~~~~~

.. autoclass:: notify.models.Account
   :members:
   :undoc-members:
   :show-inheritance:

The Account class holds provider-specific information for an actor:

.. code-block:: python

    account = Account(
        provider="email",
        address="user@example.com",
        enabled=True
    )

Actor
~~~~~

.. autoclass:: notify.models.Actor
   :members:
   :undoc-members:
   :show-inheritance:

The Actor class represents a user that can send or receive notifications:

.. code-block:: python

    sender = Actor(
        name="System",
        account=Account(
            provider="email",
            address="system@example.com"
        )
    )

    recipient = Actor(
        name="John Smith",
        account=Account(
            provider="telegram",
            userid="123456789"
        )
    )

Message Models
-----------

Message
~~~~~~

.. autoclass:: notify.models.Message
   :members:
   :undoc-members:
   :show-inheritance:

Base message class with common attributes:

.. code-block:: python

    message = Message(
        body="Hello!",
        template="welcome.html"
    )

BlockMessage
~~~~~~~~~~

.. autoclass:: notify.models.BlockMessage
   :members:
   :undoc-members:
   :show-inheritance:

Extended message class with recipient and content type:

.. code-block:: python

    message = BlockMessage(
        sender=sender,
        recipient=recipient,
        content_type="text/html",
        body="<h1>Hello!</h1>"
    )

MailMessage
~~~~~~~~~

.. autoclass:: notify.models.MailMessage
   :members:
   :undoc-members:
   :show-inheritance:

Specialized message class for emails:

.. code-block:: python

    message = MailMessage(
        sender=sender,
        recipient=recipient,
        subject="Welcome",
        body="Welcome to our service!",
        attachments=[attachment1, attachment2]
    )

Attachment Models
-------------

Attachment
~~~~~~~~

.. autoclass:: notify.models.Attachment
   :members:
   :undoc-members:
   :show-inheritance:

Base attachment class:

.. code-block:: python

    attachment = Attachment(
        name="document.pdf",
        content_type="application/pdf"
    )

MailAttachment
~~~~~~~~~~~

.. autoclass:: notify.models.MailAttachment
   :members:
   :undoc-members:
   :show-inheritance:

Email-specific attachment class:

.. code-block:: python

    attachment = MailAttachment(
        name="document.pdf",
        filename="document.pdf",
        content_type="application/pdf",
        content_disposition="attachment"
    )

Chat Models
--------

Chat
~~~~

.. autoclass:: notify.models.Chat
   :members:
   :undoc-members:
   :show-inheritance:

Represents a chat in messaging platforms:

.. code-block:: python

    chat = Chat(
        chat_name="Team Chat",
        chat_id="123456789"
    )

Channel
~~~~~~

.. autoclass:: notify.models.Channel
   :members:
   :undoc-members:
   :show-inheritance:

Represents a channel in messaging platforms:

.. code-block:: python

    channel = Channel(
        channel_name="announcements",
        channel_id="CH123456789"
    )

Teams Models
---------

TeamsChannel
~~~~~~~~~~

.. autoclass:: notify.models.TeamsChannel
   :members:
   :undoc-members:
   :show-inheritance:

Microsoft Teams channel:

.. code-block:: python

    teams_channel = TeamsChannel(
        name="General",
        channel_id="CH123456789",
        team_id="TM987654321"
    )

TeamsChat
~~~~~~~~

.. autoclass:: notify.models.TeamsChat
   :members:
   :undoc-members:
   :show-inheritance:

Microsoft Teams chat:

.. code-block:: python

    teams_chat = TeamsChat(
        name="Project Discussion",
        chat_id="19:123456789",
        team_id="TM987654321"
    )

TeamsCard
~~~~~~~~

.. autoclass:: notify.models.TeamsCard
   :members:
   :undoc-members:
   :show-inheritance:

Microsoft Teams adaptive card:

.. code-block:: python

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

TeamsSection
~~~~~~~~~~

.. autoclass:: notify.models.TeamsSection
   :members:
   :undoc-members:
   :show-inheritance:

Section within a Teams card:

.. code-block:: python

    section = TeamsSection(
        activityTitle="Task Update",
        activitySubtitle="Project X",
        facts=[
            {"name": "Status", "value": "In Progress"},
            {"name": "Due Date", "value": "2024-03-01"}
        ]
    )

TeamsAction
~~~~~~~~~

.. autoclass:: notify.models.TeamsAction
   :members:
   :undoc-members:
   :show-inheritance:

Interactive action for Teams cards:

.. code-block:: python

    action = TeamsAction(
        name="View Details",
        targets=[{
            "os": "default",
            "uri": "https://example.com/details"
        }]
    )

Model Usage Examples
----------------

Email with Attachments
~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from notify import Notify
    from notify.models import Actor, Account, MailMessage, MailAttachment

    async def send_email_with_attachment():
        # Create sender and recipient
        sender = Actor(
            name="System",
            account=Account(
                provider="email",
                address="system@example.com"
            )
        )
        
        recipient = Actor(
            name="User",
            account=Account(
                provider="email",
                address="user@example.com"
            )
        )
        
        # Create attachment
        attachment = MailAttachment(
            name="report.pdf",
            filename="report.pdf",
            content_type="application/pdf"
        )
        
        # Create message
        message = MailMessage(
            sender=sender,
            recipient=recipient,
            subject="Monthly Report",
            body="Please find attached the monthly report.",
            attachments=[attachment]
        )
        
        # Send message
        email = Notify("email")
        await email.send(message)

Teams Message with Card
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from notify import Notify
    from notify.models import TeamsChannel, TeamsCard, TeamsSection

    async def send_teams_card():
        # Create channel
        channel = TeamsChannel(
            name="Project Updates",
            channel_id="CH123456789",
            team_id="TM987654321"
        )
        
        # Create card section
        section = TeamsSection(
            activityTitle="Sprint Review",
            activitySubtitle="March 2024",
            facts=[
                {"name": "Status", "value": "Completed"},
                {"name": "Velocity", "value": "45 points"}
            ]
        )
        
        # Create card
        card = TeamsCard(
            title="Sprint Summary",
            summary="March Sprint Review",
            sections=[section]
        )
        
        # Send card
        teams = Notify("teams")
        await teams.send(
            recipient=channel,
            message=card
        )
