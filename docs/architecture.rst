Architecture and Core Classes
==========================

The async-notify library is built around several key components that work together to provide a flexible notification system:

Core Components
-------------

Notify Factory
~~~~~~~~~~~~

.. autoclass:: notify.notify.Notify
   :members:
   :undoc-members:
   :show-inheritance:

The ``Notify`` class is the main entry point and factory for creating notification providers. It dynamically loads and instantiates provider classes based on the requested provider type.

Example::

    from notify import Notify

    # Create an email provider
    email = Notify("email", username="user@example.com", password="secret")
    
    # Create a Telegram provider
    telegram = Notify("telegram", bot_token="YOUR_BOT_TOKEN")

Server Components
--------------

NotifyWorker
~~~~~~~~~~

.. autoclass:: notify.server.NotifyWorker
   :members:
   :undoc-members:
   :show-inheritance:

The ``NotifyWorker`` handles the server-side processing of notifications, supporting both Redis Streams and TCP connections.

Key features:
- Redis Streams for reliable message queuing
- Redis PUB/SUB for real-time notifications
- TCP server for direct connections
- Automatic reconnection handling
- Message persistence and acknowledgment

NotifyClient
~~~~~~~~~~

.. autoclass:: notify.server.NotifyClient
   :members:
   :undoc-members:
   :show-inheritance:

The ``NotifyClient`` provides methods for sending notifications through different transport mechanisms:
- TCP connections
- Redis PUB/SUB
- Redis Streams

Example::

    from notify.server import NotifyClient

    client = NotifyClient(
        redis_url="redis://localhost:6379/0",
        tcp_host="localhost",
        tcp_port=8991
    )

    # Send via TCP
    await client.send({"provider": "email", "to": "user@example.com"})

    # Publish to Redis channel
    await client.publish(message, "notifications")

    # Add to Redis stream
    await client.stream(message, "notification_stream")

Base Provider Classes
------------------

The library uses a hierarchy of base classes for different types of providers:

ProviderBase
~~~~~~~~~~

.. autoclass:: notify.providers.base.ProviderBase
   :members:
   :undoc-members:
   :show-inheritance:

Abstract base class for all providers, implementing core functionality:
- Connection management
- Template rendering
- Message sending logic
- Error handling

Provider Types
~~~~~~~~~~~

.. autoclass:: notify.providers.base.ProviderType
   :members:
   :undoc-members:
   :show-inheritance:

Specialized base classes for different notification types:

.. autoclass:: notify.providers.base.ProviderEmail
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: notify.providers.base.ProviderMessaging
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: notify.providers.base.ProviderIM
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: notify.providers.base.ProviderPush
   :members:
   :undoc-members:
   :show-inheritance:

Data Models
---------

The library uses several data models to represent notification components:

Actor Model
~~~~~~~~~

.. autoclass:: notify.models.Actor
   :members:
   :undoc-members:
   :show-inheritance:

Base class for both senders and recipients. Contains:
- User identification
- Account information
- Provider-specific attributes

Message Models
~~~~~~~~~~~

.. autoclass:: notify.models.Message
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: notify.models.BlockMessage
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: notify.models.MailMessage
   :members:
   :undoc-members:
   :show-inheritance:

Templates
--------

.. autoclass:: notify.templates.TemplateParser
   :members:
   :undoc-members:
   :show-inheritance:

The template system supports:
- Async rendering
- Multiple template formats
- Custom filters
- Template inheritance
