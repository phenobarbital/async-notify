import os
import uuid
from pathlib import Path
from datetime import datetime
from dataclasses import InitVar
from typing import Any, Union
from email.parser import Parser
from email.policy import default as policy_default
from datamodel import BaseModel, Column, Field


CONTENT_TYPES = [
    "text/plain",
    "text/html",
    "multipart/alternative",
    "application/json"
]


def auto_uuid(*args, **kwargs):  # pylint: disable=W0613
    return uuid.uuid4()


def now():
    return datetime.now()


class Account(BaseModel):
    """
    Attributes for using a Provider by an User (Actor)
    """

    provider: str = Column(required=True, default="dummy")
    enabled: bool = Column(required=True, default=True)
    address: Union[str, list[str]] = Column(required=False, default_factory=list)
    number: Union[str, list[str]] = Column(required=False, default_factory=list)
    userid: str = Column(required=False, default="")
    attributes: dict = Column(required=False, default_factory=dict)

    def set_address(self, address: Union[str, list[str]]):
        if isinstance(address, str):
            self.address = [address]
        else:
            self.address = address


class Actor(BaseModel):
    """
    Basic Actor (meta-definition), can be an Sender or a Recipient
    """

    userid: uuid.UUID = Field(required=False, primary_key=True, default=auto_uuid)
    name: str
    account: Union[Account, list[Account]]

    def __str__(self) -> str:
        return f"<{self.name}: {self.userid}>"


Recipient = Actor
Sender = Actor


class Chat(BaseModel):
    """
    Basic configuration for chat (message-based) notifications
    """

    chat_name: str = Column(required=False)
    chat_id: str = Column(required=True, primary_key=True)


class Channel(BaseModel):
    """
    Basic configuration for Channel (Group-based) notifications.
    """

    channel_name: str = Column(required=False)
    channel_id: str = Column(required=True, primary_key=True)


class Message(BaseModel):
    """
    Message.
    Base-class for Message blocks for Notify
    TODO:
     * template needs a factory function to find a jinja processor
     *
    """

    name: str = Column(required=True, default=auto_uuid)
    body: Union[str, dict] = Column(default=None)
    content: str = Column(required=False, default="")
    sent: datetime = Column(required=False, default=now)
    template: Path


class Attachment(BaseModel):
    """Attachement.

    an Attachment is any document attached to a message.
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

    sender: Union[Actor, list[Actor]] = Column(required=False)
    recipient: Union[Actor, list[Actor]] = Column(required=False)
    content_type: CONTENT_TYPES = Column(default_factory=CONTENT_TYPES)
    attachments: list[Attachment] = Column(default_factory=list)
    flags: list[str]


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
    attachments: list[MailAttachment]
    raw: InitVar = ""

    def __post_init__(self, raw: str) -> None:  # pylint: disable=W0221
        if (msg := Parser(policy=policy_default).parsestr(raw)):
            self.subject = msg["subject"]
            self.sender = msg["from"]
            self.recipient = msg["to"]
            self.body = msg.get_body()
            self.attachments = []
            for part in msg.walk():
                if (
                    part.get_content_maintype() == "text"
                    and "attachment" not in part.get("Content-Disposition", "")
                ):
                    self.content = (
                        part.get_payload(decode=True)
                        .decode(part.get_param("charset", "ascii"))
                        .strip()
                    )
                if part.get_filename() is not None:
                    attach = MailAttachment(
                        **{
                            "name": os.path.basename(part.get_filename()),
                            "filename": part.get_filename(),
                            "content_type": part.get_content_type(),
                            "type": part.get_content_maintype(),
                            "content_disposition": part.get("Content-Disposition"),
                            "attachment": part.get_payload(decode=True),
                            "size": len(part.as_bytes()),
                        }
                    )
                    self.attachments.append(attach)
        super(MailMessage, self).__post_init__()

    def getSubject(self):
        return self.subject

    def get_attachments(self):
        return self.attachments

    def get_attachments_names(self):
        return [at.filename for at in self.attachments]


class TeamsChannel(BaseModel):
    channel_id: str
    team_id: str


class TeamsWebhook(BaseModel):
    uri: str = Column(required=True)


class TeamsTarget(BaseModel):
    os: str = Column(default='default')
    uri: str = Column(required=True)

class TeamsAction(BaseModel):
    name: str = Column(required=False, default=None)
    targets: list[TeamsTarget] = Column(default_factory=list)

class TeamsSection(BaseModel):
    activityTitle: str = Column(required=False, default=None)
    activitySubtitle: str = Column(required=False, default=None)
    activityImage: str = Column(required=False, default=None)
    facts: list[str] = Column(required=False, default_factory=list)
    text: str = Column(required=False, default=None)
    potentialAction: list[TeamsAction] = Column(required=False, default=None, default_factory=list)

class TeamsCard(BaseModel):
    summary: str
    sections: list[TeamsSection] = Column(required=False, default_factory=list)
    text: str = Column(required=False, default=None)

    def to_dict(self):
        data = super(TeamsCard, self).to_dict()
        data['@type'] = "MessageCard"
        data['@context'] = "http://schema.org/extensions"
        return data
