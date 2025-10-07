Server Components
================

async-notify includes server components for handling notifications at scale using Redis for message queuing and persistence.

Architecture
----------

The server architecture consists of these main components:

1. NotifyWorker: Handles message processing and delivery
2. NotifyClient: Sends messages to workers
3. QueueManager: Manages message queues and processing
4. Redis: Used for message persistence and pub/sub

NotifyWorker
----------

.. autoclass:: notify.server.NotifyWorker
   :members:
   :undoc-members:
   :show-inheritance:

The NotifyWorker is the main server component that:

- Listens for incoming messages via TCP
- Processes messages from Redis Streams
- Handles message acknowledgment
- Manages worker groups
- Provides message persistence

Example::

    from notify.server import NotifyWorker
    
    worker = NotifyWorker(
        host="0.0.0.0",
        port=8991,
        debug=True,
        notify_empty_stream=True
    )
    
    await worker.start()

Configuration
~~~~~~~~~~~

Workers can be configured through environment variables or constructor parameters:

.. code-block:: python

    # Environment variables
    NOTIFY_REDIS="redis://localhost:6379/5"
    NOTIFY_CHANNEL="NotifyChannel"
    NOTIFY_WORKER_STREAM="NotifyWorkerStream"
    NOTIFY_WORKER_GROUP="NotifyWorkerGroup"
    NOTIFY_DEFAULT_HOST="0.0.0.0"
    NOTIFY_DEFAULT_PORT=8991
    NOTIFY_USE_DISCOVERY=False
    NOTIFY_QUEUE_SIZE=8
    NOTIFY_QUEUE_CALLBACK="path.to.callback"

NotifyClient
----------

.. autoclass:: notify.server.NotifyClient
   :members:
   :undoc-members:
   :show-inheritance:

The NotifyClient provides methods to send messages to workers:

Example::

    from notify.server import NotifyClient
    
    client = NotifyClient(
        redis_url="redis://localhost:6379/5",
        tcp_host="localhost",
        tcp_port=8991
    )
    
    # Send via TCP
    await client.send({
        "provider": "email",
        "recipient": ["user@example.com"],
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

QueueManager
----------

.. autoclass:: notify.server.queue.QueueManager
   :members:
   :undoc-members:
   :show-inheritance:

The QueueManager handles message queuing and processing:

Example::

    from notify.server.queue import QueueManager
    
    queue = QueueManager()
    
    # Add message to queue
    await queue.put(message, id="msg-123")
    
    # Get message from queue
    message = await queue.get()
    
    # Process queued messages
    await queue.queue_handler()

NotifyWrapper
-----------

.. autoclass:: notify.server.wrapper.NotifyWrapper
   :members:
   :undoc-members:
   :show-inheritance:

The NotifyWrapper wraps messages for processing:

Example::

    from notify.server.wrapper import NotifyWrapper
    
    wrapper = NotifyWrapper(
        provider="email",
        recipient=["user@example.com"],
        message="Hello!"
    )
    
    # Process wrapped message
    result = await wrapper()

Deployment
--------

Running Workers
~~~~~~~~~~~~

Workers can be run as standalone processes or within a process manager:

.. code-block:: python

    # worker.py
    import asyncio
    from notify.server import NotifyWorker
    
    async def main():
        worker = NotifyWorker()
        await worker.start()
    
    if __name__ == "__main__":
        asyncio.run(main())

Using Supervisor::

    [program:notify-worker]
    command=python worker.py
    process_name=%(program_name)s_%(process_num)02d
    numprocs=4
    directory=/path/to/app
    autostart=true
    autorestart=true
    redirect_stderr=true
    stdout_logfile=/var/log/notify-worker.log

High Availability
~~~~~~~~~~~~~~

For high availability:

1. Run multiple workers behind a load balancer
2. Use Redis cluster for message persistence
3. Configure worker groups for message distribution
4. Enable automatic reconnection
5. Implement proper error handling and logging

Example configuration::

    NOTIFY_REDIS="redis://redis-cluster:6379/5"
    NOTIFY_WORKER_GROUP="production-workers"
    NOTIFY_QUEUE_SIZE=16
    NOTIFY_USE_DISCOVERY=True

Monitoring
~~~~~~~~

Monitor worker health and performance:

1. Enable debug logging::

    worker = NotifyWorker(debug=True)

2. Monitor empty streams::

    worker = NotifyWorker(
        notify_empty_stream=True,
        empty_stream_minutes=5
    )

3. Implement custom callbacks::

    async def message_callback(message, result):
        print(f"Message {message.id} processed with result: {result}")
    
    worker = NotifyWorker()
    worker.send_notification = message_callback

4. Use Redis monitoring tools to track queues and streams.

Error Handling
~~~~~~~~~~~

Workers implement comprehensive error handling:

1. Connection errors::

    try:
        await worker.start()
    except ConnectionError:
        # Implement reconnection logic
        pass

2. Message processing errors::

    try:
        await message()
    except Exception as e:
        # Log error and handle failed message
        logger.error(f"Failed to process message: {e}")

3. Queue management::

    try:
        await queue.put(message)
    except asyncio.queues.QueueFull:
        # Handle queue overflow
        pass

Security
-------

Secure your deployment:

1. Use TLS for Redis connections::

    NOTIFY_REDIS="rediss://redis:6379/5"

2. Enable authentication::

    NOTIFY_REDIS="redis://:password@redis:6379/5"

3. Configure network security:
   - Use private networks
   - Implement firewalls
   - Restrict access to Redis and worker ports

4. Secure message content:
   - Validate input
   - Sanitize content
   - Encrypt sensitive data
