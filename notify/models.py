import os
import uuid
from datetime import datetime
from dataclasses import InitVar
from typing import Any, Dict, List, Set, Tuple, Optional, get_type_hints, Callable, ClassVar, Union
from asyncdb.models import Model, Column
from email.parser import Parser
from email.policy import default as policy_default
from pathlib import Path

CONTENT_TYPES = [
    "text/plain",
    "text/html",
    "multipart/alternative",
    "application/json"
]


def auto_uuid(*args, **kwargs):
    return uuid.uuid4()

def now():
    return datetime.now()

class Account(Model):
    """
    Attributes for using a Provider by an User (Actor)
    """
    provider: str = Column(required=True, default='dummy')
    enabled: bool = Column(required=True, default=True)
    address: Union[str, List[str]] = Column(required=False, default='')
    phone: Union[str, List[str]] = Column(required=False, default='')

    def set_address(self, address: str):
        self.address = address


class Actor(Model):
    """
    Basic Actor (meta-definition), can be an Sender or a Recipient
    """
    userid: uuid.UUID = Column(required=True, primary_key=True, default=auto_uuid)
    name: str
    account: Union[Account, List[Account]]
    
    def __str__(self) -> str:
        return f'<{self.name}: {self.userid}>'

Recipient = Actor
Sender = Actor

class Chat(Model):
    """
    Basic configuration for chat-based notifications
    """
    chat_name: str = Column(required=False)
    chat_id: str = Column(required=True, primary_key=True)


class Message(Model):
    """
    Message.
    Base-class for Message blocks for Notify
    TODO:
     * template needs a factory function to find a jinja processor
     *
    """
    name: str = Column(required=True)
    body: Union[str, dict] = Column(default=None)
    content: str = Column(required=False, default='')
    sent: datetime = Column(required=False, default=now)
    template: Path

    def __model_init__(cls, name, attrs) -> None:
        cls.name = auto_uuid()


class Attachment(Model):
    """
    Basic Attachement
    """
    name: str = Column(required=True)
    content: Any = None
    content_type: str
    type: str


class BlockMessage(Message):
    """
    BlockMessage.
    Class for Message Notifications
    TODO:
     * template needs a factory function to find a jinja processor
     *
    """
    sender: Union[Actor, List[Actor]] = Column(required=False)
    recipient: Union[Actor, List[Actor]] = Column(required=False)
    content_type: CONTENT_TYPES = Column(default_factory=CONTENT_TYPES)
    attachments: List[Attachment] = Column(default_factory=list)
    flags: List[str]



class MailAttachment(Attachment):
    subject: str = Column(required=False)
    filename: str
    content_disposition: str
    attachment: Any
    size: int


class MailMessage(BlockMessage):
    """
    MailMessage.
    Dataclass for representing an Email Object.
    """

    # TODO: add validation for path-like objects using pathlib
    directory: str = Column(required=True)
    content: str = Column(required=False)
    attachments: List[MailAttachment]
    raw: InitVar = ''

    def __post_init__(self, raw: str) -> None:
        msg = Parser(policy=policy_default).parsestr(raw)
        if msg:
            self.subject = msg['subject']
            self.sender = msg['from']
            self.recipient = msg['to']
            self.body = msg.get_body()
            self.attachments = []
            for part in msg.walk():
                if part.get_content_maintype() == 'text' and 'attachment' not in part.get('Content-Disposition', ''):
                    self.content = part.get_payload(decode=True).decode(part.get_param('charset', 'ascii')).strip()
                if part.get_filename() is not None:
                    attach = MailAttachment(**{
                        "name": os.path.basename(part.get_filename()),
                        "filename": part.get_filename(),
                        "content_type": part.get_content_type(),
                        "type": part.get_content_maintype(),
                        "content_disposition": part.get('Content-Disposition'),
                        "attachment": part.get_payload(decode=True),
                        'size': len(part.as_bytes())
                    })
                    self.attachments.append(attach)
        super(MailMessage, self).__post_init__()

    def getSubject(self):
        return self.subject

    def get_attachments(self):
        return self.attachments

    def get_attachments_names(self):
        return [at.filename for at in self.attachments]
