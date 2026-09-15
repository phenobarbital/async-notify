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

Microsoft Office 365 email provider, sending mail through **Microsoft
Graph** (``msgraph-sdk``) — one Graph message per ``send()`` call, to
every recipient. It does **not** read mail, calendar, contacts, or
schedule meetings; those are out of scope.

Features:

- Four auth flows behind one MSAL-backed async credential:
  ``client_credentials`` (app-only, secret **or** certificate),
  ``on_behalf_of`` (OAuth2 OBO — a signed-in user's token exchanged for a
  Graph token), ``delegated`` (device-code bootstrap, then silent cached
  refresh), and ``password`` (legacy ROPC, ``DeprecationWarning``).
- **Send-as**: an instance default ``sender=`` overridable per send with
  ``from_address=``.
- One Graph message to **all** recipients, with To/CC/BCC/Reply-To,
  ``importance``, a ``save_to_sent_items`` switch, attachments (including
  upload sessions for files over 3 MB, up to 150 MB each), and inline CID
  images.
- Pluggable, encrypted token cache: in-memory (default), file, or Redis.
- Typed results: ``MailSendResult`` per call; auth/permission failures
  raise ``NotifyAuthError``, other Graph failures come back as a failed
  ``MailSendResult``.

Auth flow examples::

    # App-only daemon, sending as a shared mailbox
    mail = Notify(
        "office365",
        auth_flow="client_credentials",
        client_id="CLIENT_ID", client_secret="CLIENT_SECRET", tenant_id="TENANT_ID",
        sender="noreply@contoso.com",
    )
    async with mail as m:
        [result] = await m.send(
            recipient=[alice, bob], subject="Report", template="report.html",
            cc=["ops@contoso.com"], attachments=["/tmp/report.pdf"],
            inline_images={"logo": "/srv/assets/logo.png"}, importance="high",
        )
        assert result.success

    # On-Behalf-Of, from a web handler: sends as the signed-in user; one
    # long-lived instance serves many users (the assertion is per-send only)
    mail = Notify("office365", auth_flow="on_behalf_of",
                  client_id="CLIENT_ID", client_secret="CLIENT_SECRET", tenant_id="TENANT_ID")
    await mail.send(recipient=carol, subject="Approved", message=html,
                     user_assertion=request_bearer_token)
    # optional: from_address="team@contoso.com" (needs SendAs / SendOnBehalf on that mailbox)

    # Delegated: one-time headless bootstrap, then silent sends
    #   $ python -m notify.providers.office365.login --username me@contoso.com
    mail = Notify("office365", auth_flow="delegated", username="me@contoso.com",
                  client_id="CLIENT_ID", tenant_id="TENANT_ID")

    # Legacy — still works, logs DeprecationWarning (ROPC)
    mail = Notify("office365", use_credentials=True,
                  client_id="CLIENT_ID", client_secret="CLIENT_SECRET", tenant_id="TENANT_ID",
                  username="me@contoso.com", password="...")

Send-as and On-Behalf-Of, precisely:

- ``user_assertion`` is a **per-send** kwarg only (``send(user_assertion=...)``).
  Passing it to the constructor raises ``ProviderError``. It is stripped from
  the kwargs forwarded to ``sent`` callbacks and never logged.
- **Mailbox routing**: app-only (``client_credentials``) always calls
  ``/users/{mailbox}``, never ``/me`` — ``mailbox`` is ``from_address`` or
  ``sender`` and is **required** (``NotifyAuthError`` if missing). Every
  other flow (``on_behalf_of``, ``delegated``, the legacy ``password`` flow)
  calls ``/me`` and sets ``Message.from_`` when ``from_address``/``sender``
  is given.
- **OBO cannot be queued.** The notify server rejects any queued job
  carrying ``user_assertion`` with ``MessageError`` before it ever reaches
  Redis or a TCP payload — send On-Behalf-Of mail directly, never through
  ``NotifyClient``/``NotifyWrapper``.

Token store settings (``notify/conf.py``, navconfig)::

    O365_AUTH_FLOW                    # None -> resolved from constructor/settings (see below)
    O365_SENDER
    O365_CLIENT_CERTIFICATE_PATH
    O365_CLIENT_CERTIFICATE_THUMBPRINT
    O365_CLIENT_CERTIFICATE_PASSWORD
    O365_TOKEN_STORE                  # "memory" (default) | "file" | "redis"
    O365_TOKEN_STORE_DIR              # default: BASE_DIR/.o365
    O365_TOKEN_STORE_REDIS            # default: NOTIFY_REDIS
    O365_TOKEN_STORE_TTL              # seconds; 0 = no TTL
    O365_TOKEN_CIPHER_KEY             # Fernet key (urlsafe base64, 32 bytes)
    O365_TOKEN_ALLOW_UNENCRYPTED      # default False

The ``file``/``redis`` token stores **refuse to start** without
``O365_TOKEN_CIPHER_KEY`` unless ``O365_TOKEN_ALLOW_UNENCRYPTED=True`` is
explicit — a persisted cache is a live credential. Auth-flow resolution
(first match wins): the ``auth_flow`` kwarg, then ``O365_AUTH_FLOW``, then
explicit ``use_credentials=True`` (-> ``password``, deprecated), then
``client_secret``/``client_certificate_path`` present (-> ``client_credentials``),
then ``username``/``password`` present (-> ``password``, deprecated),
otherwise ``NotifyAuthError``.

Tenant prerequisites:

- App registration: application ``Mail.Send`` for app-only; delegated
  ``Mail.Send`` (+ ``Mail.Send.Shared`` for shared mailboxes) with admin
  consent for OBO/delegated; the app must be a confidential client
  (secret or certificate) to run On-Behalf-Of; "Allow public client
  flows" enabled for the device-code bootstrap.
- On-Behalf-Of additionally requires the app to expose an API scope that
  the incoming user token's ``aud`` matches.
- App-only ``Mail.Send`` can send as *any* mailbox in the tenant — scope
  it with an Exchange **Application Access Policy** (RBAC for
  Applications); this is documented here but not automated by this
  provider.
- Send-as a shared mailbox or another user (``from_address``/``sender``)
  needs Exchange **SendAs** or **SendOnBehalf** rights on that mailbox.

Bootstrap the delegated flow headlessly (no browser redirect)::

    python -m notify.providers.office365.login --username me@contoso.com \
        [--tenant-id TENANT_ID] [--client-id CLIENT_ID] [--token-store file|redis]

``--token-store memory`` is refused (exit code 2) — an in-memory cache is
lost as soon as the process exits, defeating the point of bootstrapping.

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

``Outlook`` is a **backward-compatible alias of the Graph-based
``office365`` provider** — same constructor, same four auth flows, same
``send()`` behavior. It is kept only so existing ``Notify("outlook",
...)`` callers keep working; it does not stay a silent alias by
accident — this is a deliberate design decision, and it does **not**
emit a deprecation warning.

Features:

- Everything ``office365`` supports (see above): app-only / OBO /
  delegated / legacy password auth, send-as, attachments, inline CID
  images, pluggable encrypted token stores.
- The legacy ``add_attachment(filename)`` queueing API is preserved for
  existing callers: a queued file attaches to the *next* ``send()`` call
  and the queue is cleared afterward (even if that send fails). A
  missing path raises ``FileNotFoundError`` immediately, as before.

Example::

    outlook = Notify(
        "outlook",
        auth_flow="client_credentials",
        client_id="CLIENT_ID", client_secret="CLIENT_SECRET", tenant_id="TENANT_ID",
        sender="noreply@contoso.com",
    )
    async with outlook as o:
        await o.add_attachment("/tmp/report.pdf")
        [result] = await o.send(recipient=[alice], subject="Report", message="<p>See attached.</p>")
        assert result.success

.. note::
   The previous ``Outlook`` implementation depended on
   ``Office365-REST-Python-Client`` (``office365.graph_client.GraphClient``),
   which is broken and has been removed entirely, along with its direct
   ``acquire_token()`` / ``acquire_token_by_username()`` methods — see the
   Migration Notes below.

.. autoclass:: notify.providers.outlook.outlook.Outlook
   :members:
   :undoc-members:
   :show-inheritance:

Migration Notes: ``office365`` / ``outlook`` on Microsoft Graph
-----------------------------------------------------------------

Both providers were rewritten on Microsoft Graph (``msgraph-sdk``). If
you use either, review these behavior changes:

- **Removed dependencies**: ``o365``, ``pyo365``, and
  ``Office365-REST-Python-Client`` are gone from the ``azure``/``all``
  extras — no code path in either provider imports ``O365``, the
  ``office365`` REST client, or ``pyo365`` anymore. ``cryptography`` is
  now an explicit dependency (it encrypts persistent token caches).
- **``use_credentials`` default changed**: it used to default to ``True``
  (basic-auth/ROPC). It now defaults to ``None``, so a caller with
  ``client_secret``/certificate settings and no explicit
  ``use_credentials=True`` resolves to ``client_credentials`` (app-only)
  instead — and app-only now **requires** ``sender``/``from_address``.
- **App-only requires a mailbox**: pass ``sender=`` (or ``from_address=``
  per send) — previously the mailbox was implicit / unchecked.
- **Template context changed for batched sends**: ``recipient``/``username``
  in a template is now the **full recipient list** (one render, one Graph
  message to everyone), not a single ``Actor``. Templates that used
  ``recipient.name`` must iterate the list instead.
- **Removed API**: ``Outlook.acquire_token()`` and
  ``Outlook.acquire_token_by_username()`` are gone, and the old
  ``.o365_token.txt`` file is no longer read or written.
- **No more interactive ``input()``**: the previous first-run
  authorization-code prompt is removed entirely. Delegated auth now
  bootstraps headlessly via ``python -m notify.providers.office365.login``
  (device code), then refreshes silently from the cached token.
- **New send-time kwargs**: ``cc``, ``bcc``, ``reply_to``, ``importance``,
  ``attachments`` (upload sessions above 3 MB, up to 150 MB/file),
  ``inline_images`` (CID), ``from_address``, ``save_to_sent_items``, and
  ``user_assertion`` (On-Behalf-Of, per-send only — see above).
- **Queued OBO is rejected**: sending On-Behalf-Of through the notify
  server (``NotifyClient``/``NotifyWrapper``) raises ``MessageError`` —
  send OBO mail directly instead.

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