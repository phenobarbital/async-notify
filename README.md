# Async-Notify #

Async-Notify is a simple, asyncio-based notification library for Apps.

Notify is built on top of python asyncio for send notifications asynchronous with support of twilio, telegram, o365, email, slack, onesignal and many others.

### Why Async-Notify? ###

The finality of Async-Notify is to provide us a subset of communication providers for sending different notifications in a non-blocking mode..
The main goal of Async-Notify is using only asyncio-based technologies.

### Requirements ###

* Python >= 3.8
* asyncio (https://pypi.python.org/pypi/asyncio/)

### Quick Tutorial ###

Currently Async-Notify supports the following providers:

* Amazon SES
* Email (SMTP)
* Gmail
* Office 365
* Telegram (requires aiogram)
* Twilio (SMS)
* OneSignal
* Twitter
* XMPP stanzas

### Templates ###

`send(template=...)` accepts either a template **filename** (resolved on
`TEMPLATE_DIR`, unchanged since earlier versions) or raw **Jinja2 source
text**, auto-detected by a conservative heuristic (a Jinja2 delimiter
`{{`, `{%`, `{#`, or a line break means source; anything else is treated as
a filename). Use `template_is_source=True`/`False` to force either
interpretation when the heuristic can't decide (for example a body with no
Jinja markup and no newline, which is indistinguishable from a filename).

```python
# raw source — new in 1.6.0
await Notify("smtp").send(
    recipient=[actor],
    subject="Welcome",
    template="<p>Hola {{ recipient.account.address }} — {{ message }}</p>",
    message="…",
)

# filename — unchanged behaviour
await Notify("smtp").send(recipient=[actor], template="welcome.html")

# forced, for a body with no Jinja markup
await Notify("telegram").send(
    recipient=[chat], template="Hello world", template_is_source=True,
)
```

**Security note**: `autoescape` is disabled, so a template compiled from a
string executes arbitrary Jinja2 and emits unescaped output. Template
*source* must come from trusted operators (configuration, database rows
written by staff) — never from end-user input. End-user data belongs in the
message **parameters**, not in the template body itself.

#### Future work: ####

* Slack
* Facebook Messenger
* Discord
* IRC

### How do I get set up? ###

* Summary of set up
* Configuration
* Dependencies
* Database configuration
* How to run tests
* Deployment instructions

### Contribution guidelines ###

Please have a look at the Contribution Guide

* Writing tests
* Code review

### Who do I talk to? ###

* Repo owner or admin
* Other community or team contact

### License ###

Async-Notify is copyright of Jesus Lara (https://phenobarbital.info) and is licensed under BSD license. I am providing code in this repository under an open source licenses, remember, this is my personal repository; the license that you receive is from me and not from my employeer.
