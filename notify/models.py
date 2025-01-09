import os
import uuid
from pathlib import Path
from datetime import datetime
from dataclasses import InitVar
from typing import Any, List, Union, Optional
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

    provider: str = Field(required=True, default="dummy")
    enabled: bool = Field(required=True, default=True)
    address: Union[str, list[str]] = Field(required=False, default_factory=list)
    number: Union[str, list[str]] = Field(required=False, default_factory=list)
    userid: str = Field(required=False, default="")
    attributes: dict = Field(required=False, default_factory=dict)

    def set_address(self, address: Union[str, list[str]]):
        self.address = [address] if isinstance(address, str) else address


class Actor(BaseModel):
    """
    Basic Actor (meta-definition), can be an Sender or a Recipient
    """

    userid: uuid.UUID = Field(required=False, primary_key=True, default=auto_uuid)
    name: str
    account: Optional[Account]
    accounts: Optional[list[Account]]

    def __str__(self) -> str:
        return f"<{self.name}: {self.userid}>"


Recipient = Actor
Sender = Actor


class Chat(BaseModel):
    """
    Basic configuration for chat (message-based) notifications
    """

    chat_name: str = Field(required=False)
    chat_id: str = Field(required=True, primary_key=True)


class Channel(BaseModel):
    """
    Basic configuration for Channel (Group-based) notifications.
    """

    channel_name: str = Field(required=False)
    channel_id: str = Field(required=True, primary_key=True)


class Message(BaseModel):
    """
    Message.
    Base-class for Message blocks for Notify
    TODO:
     * template needs a factory function to find a jinja processor
     *
    """

    name: str = Field(required=True, default=auto_uuid)
    body: Union[str, dict] = Field(default=None)
    content: str = Field(required=False, default="")
    sent: datetime = Field(required=False, default=now)
    template: Path


class Attachment(BaseModel):
    """Attachement.

    an Attachment is any document attached to a message.
    """

    name: str = Field(required=True)
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

    sender: Union[Actor, list[Actor]] = Field(required=False)
    recipient: Union[Actor, list[Actor]] = Field(required=False)
    content_type: CONTENT_TYPES = Field(default_factory=CONTENT_TYPES)
    attachments: list[Attachment] = Field(default_factory=list)
    flags: list[str]


class MailAttachment(Attachment):
    subject: str = Field(required=False)
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
    directory: str = Field(required=True)
    content: str = Field(required=False)
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
    name: str
    channel_id: str
    team_id: str

class TeamsChat(BaseModel):
    name: str
    chat_id: str
    team_id: str

class TeamsWebhook(BaseModel):
    uri: str = Field(required=True)


class TeamsTarget(BaseModel):
    os: str = Field(default='default')
    uri: str = Field(required=True)

class TeamsAction(BaseModel):
    name: str = Field(required=False, default=None)
    targets: list[TeamsTarget] = Field(default_factory=list)

class TeamsSection(BaseModel):
    activityTitle: str = Field(required=False, default=None)
    activitySubtitle: str = Field(required=False, default=None)
    activityImage: str = Field(required=False, default=None)
    facts: list[dict] = Field(required=False, default_factory=list)
    text: str = Field(required=False, default=None)
    potentialAction: list[TeamsAction] = Field(required=False, default=None, default_factory=list)

    def addFacts(self, facts: list):
        self.facts = facts

    def to_adaptative(self):
        items = []

        if self.activityTitle:
            items.append({
                "type": "TextBlock",
                "size": "medium",
                "weight": "bolder",
                "text": self.activityTitle
            })
        if self.activitySubtitle:
            items.append({
                "type": "TextBlock",
                "spacing": "none",
                "weight": "bold",
                "text": self.activitySubtitle
            })
        if self.activityImage:
            items.append({
                "type": "Image",
                "size": "small",
                "url": self.activityImage
            })
        if self.facts:
            items.append({
                "type": "FactSet",
                "facts": self.facts
            })

        return {
            "type": "Container",
            "items": items
        }

class CardAction(BaseModel):
    type: str = Field(required=False, default=None)
    title: str = Field(required=False, default=None)
    data: dict = Field(required=False, default_factory={})


class TeamsCard(BaseModel):
    card_id: uuid.UUID = Field(required=False, default=auto_uuid, repr=False)
    content_type: str = Field(required=False, default="application/vnd.microsoft.card.adaptive", repr=False)
    summary: str
    sections: list[TeamsSection] = Field(required=False, default_factory=list)
    text: str = Field(required=False, default=None)
    title: str = Field(required=False, default=None)
    body_objects: List[dict] = Field(required=False, default_factory=list, repr=False)
    actions: List[CardAction] = Field(required=False, default_factory=list, repr=False)
    version: str = Field(required=False, default="1.5")

    def __post_init__(self):
        if self.version == "1.6":
            self.version = "1.5"
        return super().__post_init__()

    def addAction(self, type: str, title: str, **kwargs):
        self.actions.append(
            CardAction(type, title, data=kwargs)
        )

    def addSection(self, **kwargs):
        section = TeamsSection(**kwargs)
        self.sections.append(section)
        return section

    def addInput(self, id: str, label: str, is_required: bool = False, errorMessage: str = None, style: str = None):
        element = {
            "type": "Input.Text",
            "id": id,
            "label": label,
            "isRequired": is_required
        }
        if errorMessage is not None:
            element["errorMessage"] = errorMessage
        if style is not None:
            element["style"] = style
        if element:
            self.body_objects.append(
                element
            )

    def to_dict(self):
        data = super(TeamsCard, self).to_dict()
        del data['card_id']
        del data['body_objects']
        del data['actions']
        data['@type'] = "MessageCard"
        data['@context'] = "http://schema.org/extensions"
        return data

    def to_adaptative(self) -> dict:
        body = []
        if self.title:
            body.append({
                "type": "TextBlock",
                "size": "Medium",
                "weight": "Bolder",
                "text": self.title,
                "horizontalAlignment": "Center",
                "wrap": True,
                "style": "heading"
            })
        if self.summary:
            body.append({
                "type": "TextBlock",
                "size": "large",
                "weight": "bolder",
                "text": self.summary
            })
        if self.text:
            body.append({
                "type": "TextBlock",
                "text": self.text,
                "wrap": True
            })
        if self.sections:
            sections = []
            body.append({
                "type": "Container",
                "items": sections
            })
            sections.extend(section.to_adaptative() for section in self.sections)
        if self.body_objects:
            body.extend(iter(self.body_objects))
        if self.actions:
            actions = [action.to_dict() for action in self.actions]
            body.append({
                "actions": actions
            })

        return {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": self.version,
            "contentType": "application/vnd.microsoft.card.adaptive",
            "metadata": {
                "webUrl": "https://contoso.com/tab"
            },
            "body": body
        }
