import logging
from io import BytesIO
from pathlib import PurePath
from typing import (
    Union,
    Any
)
import emoji
from PIL import Image
# telegram
from aiogram import Bot, types
# from aiogram.dispatcher import Dispatcher
# from aiogram.dispatcher.webhook import SendMessage
from aiogram.utils.exceptions import (
    TelegramAPIError,
    # BotBlocked,
    BadRequest,
    MessageError,
    Unauthorized,
    NetworkError,
    ChatNotFound
)
import aiofiles
# from aiogram.utils.emoji import emojize
# from aiogram.utils.markdown import bold, code, italic, text
# TODO: web-hooks
# from aiogram.utils.executor import start_webhook
from notify.models import Actor, Chat
from notify.exceptions import notifyException
from notify.providers.abstract import ProviderIM, ProviderType
from .settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

aiogram_logger = logging.getLogger('aiogram')
aiogram_logger.setLevel(logging.WARNING)

class Telegram(ProviderIM):
    provider: str = 'telegram'
    provider_type = ProviderType.IM
    blocking: bool = False
    parseMode: str = 'html'  # can be MARKDOWN_V2 or HTML

    def __init__(self, *args, **kwargs):
        try:
            self.parseMode = kwargs['parse_mode']
            del kwargs['parse_mode']
        except KeyError:
            self.parseMode = 'html'
        self._bot = None
        self._info = None
        self._bot_token = None
        self._chat_id: str = None
        self._connected: bool = False
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


    async def close(self):
        self._bot = None
        self._connected = False

    async def connect(self, *args, **kwargs):
        # creation of bot
        try:
            self._bot = Bot(token=self._bot_token)
            self._info = await self._bot.get_me()
            self._logger.debug(
                f"🤖 Hello, I'm {self._info.first_name}.\nHave a nice Day!"
            )
            self._connected = True
        except Exception as err:
            raise notifyException(
                f"Notify: Error creating Telegram Bot {err}"
            ) from err

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

    async def _send_(
            self,
            to: Union[str, Actor, Chat],
            message: Any = None,
            subject: str = None,
            **kwargs
        ): # pylint: disable=W0221
        """
        _send_.

        Logic associated with the construction of notifications
        """
        # start sending a message:
        try:
            msg = await self._render_(to, message, subject=subject, **kwargs)
            self._logger.info(f'Messsage> {msg}')
        except Exception as err:
            raise RuntimeError(
                f'Notify Telegram: Error Parsing Message: {err}'
            ) from err
        # Parsing Mode:
        if self.parseMode == 'html':
            mode = types.ParseMode.HTML
        else:
            mode = types.ParseMode.MARKDOWN_V2
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
            response = await self._bot.send_message(
                **args
            )
            # TODO: make the processing of response
            return response
        except Unauthorized as err:
            # remove update.message.chat_id from conversation list
            print(err)
        except ChatNotFound as err:
            # the chat_id of a group has changed, use e.new_chat_id instead
            print(err)
        except BadRequest as err:
            # handle malformed requests - read more below!
            print(err)
        except NetworkError as err:
            # handle slow connection problems
            print(err)
        except TelegramAPIError as err:
            # handle all other telegram related errors
            print(err)
        except Exception as err:
            print('ERROR: ', err)


    async def prepare_photo(self, photo):
        # Migrate to aiofile
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

    async def send_photo(self, photo, **kwargs):
        image = await self.prepare_photo(photo)
        if image:
            chat_id = self.get_chat()
            try:
                response = await self._bot.send_photo(
                    chat_id, photo=image, **kwargs
                )
                # print(response) # TODO: make the processing of response
                return response
            except Unauthorized as err:
                # remove update.message.chat_id from conversation list
                print(err)
            except ChatNotFound as err:
                # the chat_id of a group has changed, use e.new_chat_id instead
                print(err)
            except BadRequest as err:
                # handle malformed requests - read more below!
                print(err)
            except NetworkError as err:
                # handle slow connection problems
                print(err)
            except TelegramAPIError as err:
                # handle all other telegram related errors
                print(err)
            except Exception as err:
                print('ERROR: ', err)

    async def get_document(self, doc: Union[str, PurePath, Any]) -> Any:
        if isinstance(doc, PurePath): # Path to a File:
            if doc.exists():
                async with aiofiles.open(doc, 'rb') as f:
                    content = await f.read()
                return content
            else:
                raise FileNotFoundError(
                    f"Telegram Bot: file {doc} doesn't exists."
                )
        else:
            # TODO: check if URL or get file_id
            return doc

    async def send_document(self, document, **kwargs):
        chat_id = self.get_chat()
        doc = await self.get_document(document)
        try:
            response = await self._bot.send_document(
                chat_id,
                document=doc,
                **kwargs
            )
            # print(response) # TODO: make the processing of response
            return response
        except Unauthorized as err:
            # remove update.message.chat_id from conversation list
            print(err)
        except MessageError as err:
            print(err)
        except ChatNotFound as err:
            # the chat_id of a group has changed, use e.new_chat_id instead
            print(err)
        except BadRequest as err:
            # handle malformed requests - read more below!
            print(err)
        except NetworkError as err:
            # handle slow connection problems
            print(err)
        except TelegramAPIError as err:
            # handle all other telegram related errors
            print(err)
        except Exception as err:
            print('ERROR: ', err)

    async def get_sticker(self, sticker_id):
        if isinstance(sticker_id, dict): # getting from an sticker_set
            name = sticker_id['set']
            em = sticker_id['emoji']
            print(emoji.emojize(em))
            if isinstance(em, str) and em.startswith(':'):
                em = emoji.emojize(em)
            try:
                sticker_set = await self._bot.get_sticker_set(name)
                self._logger.debug(
                    f"Set Found: {sticker_set!r}"
                )
                st = [x for x in sticker_set['stickers'] if x['emoji'] == em]
                sticker = st[0].file_id
                return sticker
            except Exception as err:
                self._logger.warning(f'Sticker finder error: {err}')
                return None
        else:
            return 'CAACAgEAAxkBAAIuOWMze9CZzg6cQaEulHqjrcRCvBh2AAK_AgACJjFuAVdTX0Nu_LoxKgQ'

    async def send_sticker(self, sticker: Union[str, Any], **kwargs):
        chat_id = self.get_chat()
        sticker = await self.get_sticker(sticker)
        try:
            response = await self._bot.send_sticker(
                chat_id,
                sticker=sticker,
                **kwargs
            )
            # print(response) # TODO: make the processing of response
            return response
        except Unauthorized as err:
            # remove update.message.chat_id from conversation list
            print(err)
        except MessageError as err:
            print(err)
        except ChatNotFound as err:
            # the chat_id of a group has changed, use e.new_chat_id instead
            print(err)
        except BadRequest as err:
            # handle malformed requests - read more below!
            print(err)
        except NetworkError as err:
            # handle slow connection problems
            print(err)
        except TelegramAPIError as err:
            # handle all other telegram related errors
            print(err)
        except Exception as err:
            print('ERROR: ', err)

    async def get_media(self, media: Union[str, PurePath, Any]) -> Any:
        if isinstance(media, PurePath): # Path to a File:
            if media.exists():
                async with aiofiles.open(media, 'rb') as f:
                    content = await f.read()
                return content
            else:
                raise FileNotFoundError(
                    f"Telegram Bot: file {media} doesn't exists."
                )
        else:
            # TODO: check if URL or get file_id
            return media

    async def send_video(self, video: Union[str, Any], **kwargs):
        chat_id = self.get_chat()
        media = await self.get_media(video)
        try:
            response = await self._bot.send_video(
                chat_id,
                video=media,
                **kwargs
            )
            # print(response) # TODO: make the processing of response
            return response
        except Unauthorized as err:
            # remove update.message.chat_id from conversation list
            print(err)
        except MessageError as err:
            print(err)
        except ChatNotFound as err:
            # the chat_id of a group has changed, use e.new_chat_id instead
            print(err)
        except BadRequest as err:
            # handle malformed requests - read more below!
            print(err)
        except NetworkError as err:
            # handle slow connection problems
            print(err)
        except TelegramAPIError as err:
            # handle all other telegram related errors
            print(err)
        except Exception as err:
            print('ERROR: ', err)

    async def send_audio(self, audio: Union[str, PurePath, Any], **kwargs):
        chat_id = self.get_chat()
        sound = await self.get_media(audio)
        try:
            response = await self._bot.send_audio(
                chat_id,
                audio=sound,
                **kwargs
            )
            # print(response) # TODO: make the processing of response
            return response
        except Unauthorized as err:
            # remove update.message.chat_id from conversation list
            print(err)
        except MessageError as err:
            print(err)
        except ChatNotFound as err:
            # the chat_id of a group has changed, use e.new_chat_id instead
            print(err)
        except BadRequest as err:
            # handle malformed requests - read more below!
            print(err)
        except NetworkError as err:
            # handle slow connection problems
            print(err)
        except TelegramAPIError as err:
            # handle all other telegram related errors
            print(err)
        except Exception as err:
            print('ERROR: ', err)
