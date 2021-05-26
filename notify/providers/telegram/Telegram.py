import os
import pprint
from io import BytesIO
from PIL import Image
from pathlib import Path, PurePath
import pathlib
from typing import List, Union
from notify.providers import ProviderIMBase, IM

# telegram
import telegram
from telegram.ext import Updater, CommandHandler
from telegram.error import (TelegramError, Unauthorized, BadRequest,
                            TimedOut, ChatMigrated, NetworkError)

from notify.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from notify.models import Actor, Chat
from notify.exceptions import notifyException

class Telegram(ProviderIMBase):
    provider = 'telegram'
    provider_type = IM
    level = ''
    _bot = None
    _bot_token: str = None
    _chat_id: str = None
    parseMode = 'html' # can be MARKDOWN_V2 or HTML

    def __init__(self, *args, **kwargs):
        super(Telegram, self).__init__(*args, **kwargs)
        # connection related settings
        try:
            self._bot_token = kwargs['bot_token']
        except KeyError:
            self._bot_token = TELEGRAM_BOT_TOKEN

        try:
            self._chat_id = kwargs['chat_id']
        except KeyError:
            self._chat_id = TELEGRAM_CHAT_ID
        # creation of bot
        try:
            self._bot = telegram.Bot(self._bot_token)
        except Exception as err:
            raise notifyException(err)

    def close(self):
        self._bot = None

    def connect(self):
        info = None
        try:
            info = self._bot.get_me()
        except Exception as err:
            raise notifyException(err)
        if info:
            return True
        return False

    def set_chat(self, chat):
        self._chat_id = chat

    def get_chat(self, **kwargs):
        # define destination
        try:
            chat = kwargs['chat_id']
            if isinstance(chat, Chat):
                self._chat_id = chat.chat_id
            del kwargs['chat_id']
        except KeyError:
            self._chat_id = TELEGRAM_CHAT_ID
        return self._chat_id

    async def _send(self, to: Union[str, Actor, Chat], message: str, **kwargs):
        """
        _send.

        Logic associated with the construction of notifications
        """
        if self.connect():
            msg = self._render(to, message, **kwargs)
            self._logger.info('Messsage> {}'.format(msg))
            if self.parseMode == 'html':
                mode = telegram.ParseMode.HTML
            else:
                mode = telegram.ParseMode.MARKDOWN_V2
            if 'chat_id' in kwargs:
                chat_id = self.get_chat(**kwargs)
            else:
                if isinstance(to, Chat):
                    chat_id = to.chat_id
                elif isinstance(to, str):
                    chat_id = to
                else:
                    chat_id = self._chat_id
            try:
                args = {
                    'chat_id': chat_id,
                    'text': msg,
                    'parse_mode': mode,
                    **kwargs
                }
                print(args)
                response = self._bot.send_message(
                    **args
                )
                print(response) # TODO: make the processing of response
                return response
            except Unauthorized as err:
                # remove update.message.chat_id from conversation list
                print(err)
            except BadRequest as err:
                # handle malformed requests - read more below!
                print(err)
            except TimedOut as err:
                # handle slow connection problems
                print(err)
            except NetworkError as err:
                # handle other connection problems
                print(err)
            except ChatMigrated as err:
                # the chat_id of a group has changed, use e.new_chat_id instead
                print(err)
            except TelegramError as err:
                # handle all other telegram related errors
                print(err)
            except Exception as err:
                print(err)


    def prepare_photo(self, photo):
        if isinstance(photo, PurePath):
            # is a path, I need to open that image
            img = Image.open(r"{}".format(photo))
            bio = BytesIO()
            bio.name = photo.name
            img.save(bio, img.format)
            bio.seek(0)
            return bio
        elif isinstance(photo, str):
            # its an URL
            return photo
        elif isinstance(photo, BytesIO):
            # its a binary version of photo
            photo.seek(0)
            return photo
        else:
            return None

    def send_photo(self, photo, **kwargs):
        image = self.prepare_photo(photo)
        print(image)
        if image:
            chat_id = self.get_chat()
            try:
                self._response = self._bot.send_photo(chat_id, photo=image, **kwargs)
                #print(self._response) TODO: make the processing of response
            except Unauthorized as err:
                # remove update.message.chat_id from conversation list
                print(err)
            except BadRequest as err:
                # handle malformed requests - read more below!
                print(err)
            except TimedOut as err:
                # handle slow connection problems
                print(err)
            except NetworkError as err:
                # handle other connection problems
                print(err)
            except ChatMigrated as err:
                # the chat_id of a group has changed, use e.new_chat_id instead
                print(err)
            except TelegramError as err:
                # handle all other telegram related errors
                print(err)
            except Exception as err:
                print(err)

    def send_document(self, document, **kwargs):
        #doc = self.prepare_photo(document)
        #print(doc)
        #if doc:
        chat_id = self.get_chat()
        try:
            self._response = self._bot.send_document(
                chat_id,
                document=open(document, 'rb'),
                **kwargs
            )
            # print(self._response) TODO: make the processing of response
        except Unauthorized as err:
            # remove update.message.chat_id from conversation list
            print(err)
        except BadRequest as err:
            # handle malformed requests - read more below!
            print(err)
        except TimedOut as err:
            # handle slow connection problems
            print(err)
        except NetworkError as err:
            # handle other connection problems
            print(err)
        except ChatMigrated as err:
            # the chat_id of a group has changed, use e.new_chat_id instead
            print(err)
        except TelegramError as err:
            # handle all other telegram related errors
            print(err)
        except Exception as err:
            print(err)
