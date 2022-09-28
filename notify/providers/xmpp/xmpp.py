"""
xmpp.

XMPP use slixmpp to send jabber messages (XMPP protocol)
"""
import logging
import ssl
from typing import (
    Union,
    Any
)
# XMPP library
from slixmpp import ClientXMPP
from slixmpp.exceptions import IqError, IqTimeout
from slixmpp.xmlstream.xmlstream import NotConnectedError
from notify.models import Actor
from notify.providers import ProviderIMBase, IM
from notify.exceptions import ProviderError

from .settings import JABBER_JID, JABBER_PASSWORD


class Client(ClientXMPP):
    """
    Client.

    Extending Class to registering session and plugins
    """
    provider = 'xmpp'
    provider_type = IM

    def __init__(self, jid, password, plugins: list = None):
        ClientXMPP.__init__(self, jid, password)
        # The session_start event will be triggered when
        # the bot establishes its connection with the server
        # and the XML streams are ready for use. We want to
        # listen for this event so that we we can initialize
        # our roster.
        self.add_event_handler("session_start", self.session_start)
        # The message event is triggered whenever a message
        # stanza is received. Be aware that that includes
        # MUC messages and error messages.
        self.add_event_handler("message", self.message)
        self.add_event_handler("disconnected", self.on_disconnect)
        self.add_event_handler("connection_failed", self.on_connection_failure)
        if isinstance(plugins, list):
            for p in plugins:
                self.register_plugin(p)
        self['xep_0030'].add_feature('echo_demo')
        self.ssl_version = ssl.PROTOCOL_SSLv3

    async def session_start(self, event):
        self.send_presence()
        try:
            await self.get_roster()
        except IqError as err:
            logging.error('There was an error getting the roster')
            logging.error(err.iq['error']['condition'])
            self.disconnect()
        except IqTimeout:
            logging.error('Server is taking too long to respond')
            self.disconnect()

    def message(self, msg):
        """
        called by slixmpp on incoming XMPP messages
        """
        if msg['type'] in ('chat', 'normal'):
            msg.reply("Thanks for sending\n%(body)s" % msg).send()

    def on_disconnect(self, event):
        if self.do_reconnections:
            self.connect()

    def on_connection_failure(self, event):
        self.log("XMPP connection failed. Try to reconnect in 5min.")
        self.schedule(
            "Reconnect after connection failure",
            60*5,
            self.on_disconnect,
            event
        )

    async def close(self):
        logging.info("Terminating XMPP session")
        self.do_reconnections = False
        self.disconnect()
        logging.info("XMPP session terminated.")


class Xmpp(ProviderIMBase):
    """
    xmpp.

    XMPP message provider
    :param username: JID Jabber
    :param password: Jabber password
    """

    provider = 'xmpp'
    provider_type = IM
    client = None
    _session = None
    _id = None
    _plugins = [
        'xep_0030',  # Service Discovery
        'xep_0199',  # XMPP Ping
        'xep_0060',  # PubSub
        'xep_0004',  # Data Forms
    ]

    def __init__(self, username: str = None, password:str = None, **kwargs):
        """
        XMPP Provider.
        """
        super(Xmpp, self).__init__(**kwargs)

        # connection related settings
        self.username = username
        if username is None:
            self.username = JABBER_JID

        self.password = password
        if password is None:
            self.password = JABBER_PASSWORD

        if self.username is None or self.password is None:
            raise RuntimeWarning(
                f'to send emails via {self.name} you need to configure username & password. \n'
                'Either send them as function argument via key \n'
                '`username` & `password` or set up env variable \n'
                'as `GMAIL_USERNAME` & `GMAIL_PASSWORD`.'
            )
        self.actor = self.username
        if 'plugins' in kwargs and isinstance(kwargs['plugins'], list):
            self._plugins = self._plugins + kwargs['plugins']

    async def test(self, jid: str = None):
        if not jid:
            jid = self.client.boundjid.bare
        try:
            rtt = await self.client['xep_0199'].ping(jid, timeout=10)
            self._logger.info(f"Success! RTT: {rtt!s}")
        except IqError as e:
            error = e.iq['error']['condition']
            self._logger.info(f'Error pinging {jid}: {error}')
        except IqTimeout:
            self._logger.info(f'No response from {jid}')
        finally:
            self.client.disconnect()

    def connect(self):
        try:
            self.client = Client(
                self.username,
                self.password,
                plugins=self._plugins
            )
            # Connect to the XMPP server and start processing XMPP stanzas
            self.client.connect()
            self.client.process(forever=False)
        except Exception as e:
            raise ProviderError(e) from e
        return self.client

    async def _send_(self, to: Actor, message: Union[str, Any], subject: str = None, **kwargs) -> Any:
        try:
            context = kwargs['context']
        except KeyError:
            context = None
        try:
            self.client.send_message(
                mto=to,
                mbody=f"{subject}: {message}",
                mtype='chat'
            )
        except NotConnectedError:
            self.log("Message NOT SENT, not connected.")
        except IqError as e:
            raise ProviderError(e) from e
        except IqTimeout as e:
            raise ProviderError(e) from e
        except Exception as e:
            raise ProviderError(e) from e

    async def close(self):
        await self.client.close()
