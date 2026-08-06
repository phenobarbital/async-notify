Providers
=========

The async-notify library supports multiple notification providers, each with specific capabilities and configuration options.

Provider Types
------------

The library categorizes providers into several types:

- **Email Providers**: SMTP, Gmail, Office 365, AWS SES
- **Instant Messaging**: Telegram, Slack, Teams
- **SMS/Phone**: Twilio, Dialpad
- **Push Notifications**: OneSignal

Common Features
------------

All providers share these capabilities:

- Async/await interface
- Template support
- Attachment handling (where applicable)
- Error handling and retries
- Connection pooling

Template Support
-----------------

Every provider that routes through ``ProviderBase._prepare_`` — which is all
of them except OneSignal (see below) — accepts a ``template=`` keyword on
``send()``. As of ``1.6.0``, ``template=`` accepts **either**:

- a template **filename**, resolved through ``TEMPLATE_DIR`` (the original,
  unchanged behaviour), or
- raw **Jinja2 source text**, compiled on the fly.

The two are told apart by a conservative, deterministic heuristic
(``notify.templates.is_template_source``): *source* is detected only when
the value contains a Jinja2 delimiter (``{{``, ``{%``, ``{#``) or a line
break. Anything else — ``"email.html"``, ``"notifications/welcome.txt"`` —
is treated as a filename, so every existing caller is unaffected.

Use ``template_is_source=`` to override the heuristic explicitly:

- ``template_is_source=None`` (default) — auto-detect via the rules above.
- ``template_is_source=True`` — always compile *template* as Jinja2 source.
- ``template_is_source=False`` — always resolve *template* as a filename
  (exact pre-1.6.0 behaviour).

**Caveat**: a template body with no Jinja2 markup and no line break (for
example ``"Hello world"``) is indistinguishable from a filename and will be
looked up on disk, raising ``FileNotFoundError``. Pass
``template_is_source=True`` for that case.

Example::

    # raw source — new in 1.6.0
    await Notify("smtp").send(
        recipient=[actor],
        subject="Welcome",
        template="<p>Hola {{ recipient.account.address }} — {{ message }}</p>",
        message="…",
    )

    # filename — unchanged from pre-1.6.0
    await Notify("smtp").send(recipient=[actor], template="welcome.html")

    # forced, for a body with no Jinja markup
    await Notify("telegram").send(
        recipient=[chat], template="Hello world", template_is_source=True,
    )

**Security — template source is executable.** ``autoescape`` is disabled
(and stays disabled), so a template compiled from a string executes
arbitrary Jinja2 (attribute traversal, loops, registered globals and
filters) and emits **unescaped** output. Template *source* must come from
trusted operators — configuration, or database rows written by staff. Never
build it from end-user input. End-user data belongs in the **parameters**,
which are only ever substituted as values::

    # SAFE — user data is a parameter
    await notify.send(recipient=[actor], template=body_from_db, name=user_input)

    # UNSAFE — user data becomes template code
    await notify.send(recipient=[actor], template=f"<p>Hi {user_input}</p>")

Compiled string templates are cached in a bounded LRU (default size 128,
tunable via ``TemplateParser(..., string_cache_size=N)``) keyed by a hash of
the source, so re-sending the same body does not recompile it. See
``api.rst`` ("templates") for the full ``TemplateParser`` reference.

**OneSignal does not support templates** (file or string) — its ``send()``
overrides the base implementation without calling ``_prepare_``.

Configuration
-----------

Providers can be configured through:

1. Environment variables
2. Direct parameters in constructor
3. Configuration files

Example::

    from notify import Notify
    
    # Using environment variables
    email = Notify("email")
    
    # Direct configuration
    email = Notify(
        "email",
        username="user@example.com",
        password="secret",
        host="smtp.example.com"
    )

Available Providers
----------------

``aws``
---------

AWS SES (Simple Email Service) provider for sending emails through Amazon's infrastructure.

Features:
- Template support
- Attachment handling
- Rate limiting awareness

Example::

    aws = Notify(
        "aws",
        aws_access_key_id="KEY",
        aws_secret_access_key="SECRET",
        region_name="us-east-1"
    )
    
    await aws.send(
        recipient=["user@example.com"],
        subject="Test",
        message="Hello from AWS SES"
    )

.. autoclass:: notify.providers.aws.aws.Aws
   :members:
   :undoc-members:
   :show-inheritance:

``dummy``
-------------

Test provider that logs messages instead of sending them. Useful for development and testing.

Example::

    dummy = Notify("dummy")
    await dummy.send(
        recipient=["test@example.com"],
        message="Test message"
    )

.. autoclass:: notify.providers.dummy.dummy.Dummy
   :members:
   :undoc-members:
   :show-inheritance:

``email``
----------

Standard SMTP email provider supporting various email servers.

Features:
- TLS/SSL support
- HTML emails
- Attachments
- Template support

Example::

    email = Notify(
        "email",
        username="user@example.com",
        password="secret",
        hostname="smtp.example.com",
        port=587
    )

.. autoclass:: notify.providers.email.email.Email
   :members:
   :undoc-members:
   :show-inheritance:

``gmail``
-----------

Gmail-specific provider using Gmail's SMTP or API.

Features:
- OAuth2 support
- Labels and folders
- Thread management

Example::

    gmail = Notify(
        "gmail",
        username="user@gmail.com",
        password="app_specific_password"
    )

.. autoclass:: notify.providers.gmail.gmail.Gmail
   :members:
   :undoc-members:
   :show-inheritance:

``office365``
--------------

Microsoft Office 365 email provider using Microsoft Graph API.

Features:
- OAuth2 authentication
- Shared mailbox support
- Calendar integration
- Meeting scheduling

Example::

    o365 = Notify(
        "office365",
        client_id="CLIENT_ID",
        client_secret="CLIENT_SECRET",
        tenant_id="TENANT_ID"
    )

.. autoclass:: notify.providers.office365.office365.Office365
   :members:
   :undoc-members:
   :show-inheritance:

``sendgrid``
-------------

SendGrid email service provider.

Features:
- Template support
- Bulk sending
- Analytics integration

Example::

    sendgrid = Notify(
        "sendgrid",
        api_key="YOUR_API_KEY"
    )

.. autoclass:: notify.providers.sendgrid.sendgrid.Sendgrid
   :members:
   :undoc-members:
   :show-inheritance:

``slack``
------------

Slack messaging provider using Slack's Web API and Bolt framework.

Features:
- Channel messages
- Direct messages
- Rich message formatting
- Interactive components
- File sharing

Example::

    slack = Notify(
        "slack",
        bot_token="xoxb-your-token",
        signing_secret="your-signing-secret"
    )
    
    await slack.send(
        channel="#general",
        message="Hello from async-notify!"
    )

.. autoclass:: notify.providers.slack.slack.Slack
   :members:
   :undoc-members:
   :show-inheritance:

``telegram``
-------------

Telegram Bot API provider for sending messages through Telegram.

Features:
- Text messages
- Media messages (photos, videos, documents)
- Reply markup (keyboards)
- Stickers and animations
- Group chat support

Example::

    telegram = Notify(
        "telegram",
        bot_token="YOUR_BOT_TOKEN",
        chat_id="YOUR_CHAT_ID"
    )
    
    # Send text message
    await telegram.send(message="Hello!")
    
    # Send photo
    await telegram.send_photo("path/to/photo.jpg")

.. autoclass:: notify.providers.telegram.Telegram.Telegram
   :members:
   :undoc-members:
   :show-inheritance:

``twilio``
------------

Twilio provider for SMS and voice calls.

Features:
- SMS messaging
- Voice calls
- WhatsApp integration
- Phone number validation

Example::

    twilio = Notify(
        "twilio",
        account_sid="YOUR_SID",
        auth_token="YOUR_TOKEN",
        from_number="+1234567890"
    )

.. autoclass:: notify.providers.twilio.twilio.Twilio
   :members:
   :undoc-members:
   :show-inheritance:

``xmpp``
------------

XMPP (Jabber) messaging provider.

Features:
- Instant messaging
- Presence information
- Multi-user chat
- File transfer

Example::

    xmpp = Notify(
        "xmpp",
        jid="user@example.com",
        password="secret"
    )

.. autoclass:: notify.providers.xmpp.xmpp.Xmpp
   :members:
   :undoc-members:
   :show-inheritance:

``smtp``
-----------

Low-level SMTP provider with full protocol control.

Features:
- Direct SMTP protocol access
- Custom headers
- Connection pooling
- SSL/TLS support

Example::

    smtp = Notify(
        "smtp",
        host="smtp.example.com",
        port=587,
        username="user",
        password="pass"
    )

.. autoclass:: notify.providers.smtp.smtp.SMTP
   :members:
   :undoc-members:
   :show-inheritance:

``dialpad``
--------------

Dialpad provider for phone calls and SMS.

Features:
- SMS messaging
- Voice calls
- Contact management

Example::

    dialpad = Notify(
        "dialpad",
        api_key="YOUR_API_KEY",
        from_number="YOUR_NUMBER"
    )

.. autoclass:: notify.providers.dialpad.dialpad.Dialpad
   :members:
   :undoc-members:
   :show-inheritance:

``teams``
------------

Microsoft Teams provider for team chat and collaboration.

Features:
- Channel messages
- Direct messages
- Adaptive Cards
- File sharing
- Meeting integration

Example::

    teams = Notify(
        "teams",
        tenant_id="TENANT_ID",
        client_id="CLIENT_ID",
        client_secret="CLIENT_SECRET"
    )
    
    # Send to channel
    await teams.send(
        channel_id="CHANNEL_ID",
        message="Hello Teams!"
    )
    
    # Send adaptive card
    await teams.send(
        channel_id="CHANNEL_ID",
        message=TeamsCard(
            title="Hello",
            text="This is an adaptive card"
        )
    )

.. autoclass:: notify.providers.teams.teams.Teams
   :members:
   :undoc-members:
   :show-inheritance:

``outlook``
--------------

Microsoft Outlook provider using Microsoft Graph API.

Features:
- Email sending
- Calendar management
- Contact integration
- Shared mailbox support

Example::

    outlook = Notify(
        "outlook",
        client_id="CLIENT_ID",
        client_secret="CLIENT_SECRET",
        tenant_id="TENANT_ID"
    )

.. autoclass:: notify.providers.outlook.outlook.Outlook
   :members:
   :undoc-members:
   :show-inheritance:

``ses``
---------

Amazon SES provider with advanced features.

Features:
- Template management
- Bulk sending
- Delivery tracking
- DKIM support

Example::

    ses = Notify(
        "ses",
        aws_access_key_id="KEY",
        aws_secret_access_key="SECRET",
        region_name="us-east-1"
    )
    
    # Send using template
    await ses.send(
        template_name="Welcome",
        template_data={"name": "User"},
        recipients=["user@example.com"]
    )

.. autoclass:: notify.providers.ses.ses.Ses
   :members:
   :undoc-members:
   :show-inheritance: