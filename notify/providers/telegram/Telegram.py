from io import BytesIO
from pathlib import PurePath
from typing import Union, Any
import emoji
from PIL import Image
from pathlib import Path
from moviepy.editor import VideoFileClip
# telegram
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram import Bot, Dispatcher
# from aiogram.dispatcher.webhook import SendMessage
# Files
from aiogram.types import FSInputFile, BufferedInputFile, URLInputFile
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramUnauthorizedError,
    TelegramNetworkError,
    TelegramNotFound,
)
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
import aiofiles
# from aiogram.utils.emoji import emojize
# from aiogram.utils.markdown import bold, code, italic, text
# TODO: web-hooks
# from aiogram.utils.executor import start_webhook
from navconfig.logging import logging
from notify.models import Actor, Chat
from notify.exceptions import NotifyException
from notify.providers.base import ProviderIM, ProviderType

from notify.conf import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID
)

aiogram_logger = logging.getLogger("aiogram")
aiogram_logger.setLevel(logging.WARNING)


class Telegram(ProviderIM):
    provider: str = "telegram"
    provider_type = ProviderType.IM
    blocking: str = 'asyncio'
    parseMode: str = "html"  # can be MARKDOWN_V2 or HTML

    def __init__(self, *args, **kwargs):
        try:
            self.parseMode = kwargs["parse_mode"]
            del kwargs["parse_mode"]
        except KeyError:
            self.parseMode = "html"
        self._bot = None
        self._dispatcher = None
        self._info = None
        self._bot_token = None
        self._chat_id: str = None
        self._connected: bool = False
        super(Telegram, self).__init__(*args, **kwargs)
        # connection related settings
        try:
            self._bot_token = kwargs["bot_token"]
        except KeyError:
            self._bot_token = TELEGRAM_BOT_TOKEN
        try:
            self._chat_id = kwargs["chat_id"]
        except KeyError:
            self._chat_id = TELEGRAM_CHAT_ID

    def bot(self):
        return self._bot

    async def close(self):
        try:
            if self._bot:
                await self._bot.session.close()  # Close the bot's session
            await self._dispatcher.stop()
        except Exception:
            pass
        finally:
            self._bot = None
            self._connected = False

    async def connect(self, *args, **kwargs):
        # creation of bot
        try:
            self._session = AiohttpSession()
            bot_settings = {"session": self._session, "parse_mode": ParseMode.HTML}
            # bot_settings = {"parse_mode": ParseMode.HTML}
            self._bot = Bot(token=self._bot_token, **bot_settings)
            storage = MemoryStorage()
            self._dispatcher = Dispatcher(storage=storage)
            self._info = await self._bot.get_me()
            self.logger.debug(
                f"🤖 Hello, I'm {self._info.first_name}.\nHave a nice Day!"
            )
            self._connected = True
        except Exception as err:
            raise NotifyException(
                f"Notify: Error creating Telegram Bot {err}"
            ) from err

    def set_chat(self, chat):
        self._chat_id = chat

    def get_chat(self, **kwargs):
        # define destination
        try:
            chat = kwargs["chat_id"]
            if isinstance(chat, Chat):
                self._chat_id = chat.chat_id
            del kwargs["chat_id"]
        except KeyError:
            self._chat_id = TELEGRAM_CHAT_ID
        return self._chat_id

    async def _send_(
        self,
        to: Union[str, Actor, Chat],
        message: Any = None,
        subject: str = None,
        **kwargs,
    ):  # pylint: disable=W0221
        """
        _send_.

        Logic associated with the construction of notifications
        """
        # start sending a message:
        try:
            msg = await self._render_(to, message, subject=subject, **kwargs)
            self.logger.info(
                f"Messsage> {msg}"
            )
        except Exception as err:
            raise RuntimeError(
                f"Notify Telegram: Error Parsing Message: {err}"
            ) from err
        # Parsing Mode:
        if self.parseMode == "html":
            mode = ParseMode.HTML
        else:
            mode = ParseMode.MARKDOWN_V2
        if "chat_id" in kwargs:
            chat_id = self.get_chat(**kwargs)
        else:
            if isinstance(to, Chat):
                chat_id = to.chat_id
            elif isinstance(to, str):
                chat_id = to
            else:
                chat_id = self._chat_id
        try:
            args = {"chat_id": chat_id, "text": msg, "parse_mode": mode, **kwargs}
            print(args)
            response = await self._bot.send_message(**args)
            # TODO: make the processing of response
            return response
        except TelegramUnauthorizedError as err:
            # remove update.message.chat_id from conversation list
            print(err)
        except TelegramNotFound as err:
            # the chat_id of a group has changed, use e.new_chat_id instead
            print(err)
        except TelegramBadRequest as err:
            # handle malformed requests - read more below!
            print(err)
        except TelegramNetworkError as err:
            # handle slow connection problems
            print(err)
        except TelegramAPIError as err:
            # handle all other telegram related errors
            print(err)
        except Exception as err:
            print("ERROR: ", err)
            raise NotifyException(
                f"{err}"
            ) from err

    async def prepare_photo(self, photo):
        # Migrate to aiofile
        if isinstance(photo, PurePath):
            # is a path, I need to open that image
            return FSInputFile(
                photo, filename=photo.name
            )
        elif isinstance(photo, str):
            if photo.startswith("http"):
                # its an URL
                return URLInputFile(photo)
            # its an URL
            return FSInputFile(photo)
        elif isinstance(photo, BytesIO):
            # its a binary version of photo
            photo.seek(0)
            return BufferedInputFile(
                photo, filename="photo.jpg"
            )
        else:
            return None

    async def send_photo(self, photo, **kwargs):
        image = await self.prepare_photo(photo)
        if image:
            chat_id = self.get_chat()
            try:
                response = await self._bot.send_photo(chat_id, photo=image, **kwargs)
                # print(response) # TODO: make the processing of response
                return response
            except TelegramUnauthorizedError as err:
                # remove update.message.chat_id from conversation list
                print(err)
            except TelegramNotFound as err:
                # the chat_id of a group has changed, use e.new_chat_id instead
                print(err)
            except TelegramBadRequest as err:
                # handle malformed requests - read more below!
                print(err)
            except TelegramNetworkError as err:
                # handle slow connection problems
                print(err)
            except TelegramAPIError as err:
                # handle all other telegram related errors
                print(err)
            except Exception as err:
                raise NotifyException(
                    f"{err}"
                ) from err

    async def get_document(self, doc: Union[str, PurePath, Any]) -> Any:
        if isinstance(doc, PurePath):  # Path to a File:
            if doc.exists():
                return FSInputFile(doc, filename=doc.name)
            else:
                raise FileNotFoundError(
                    f"Telegram Bot: file {doc} doesn't exists."
                )
        elif isinstance(doc, str):
            if doc.startswith("http"):
                # its an URL
                return URLInputFile(doc)
            # its an URL
            return FSInputFile(doc)
        elif isinstance(doc, BytesIO):
            # its a binary version of photo
            doc.seek(0)
            return BufferedInputFile(
                doc, filename="document.txt"
            )
        else:
            return FSInputFile(doc)

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
        except TelegramUnauthorizedError as err:
            # remove update.message.chat_id from conversation list
            print(err)
        except TelegramNotFound as err:
            # the chat_id of a group has changed, use e.new_chat_id instead
            print(err)
        except TelegramBadRequest as err:
            # handle malformed requests - read more below!
            print(err)
        except TelegramNetworkError as err:
            # handle slow connection problems
            print(err)
        except TelegramAPIError as err:
            # handle all other telegram related errors
            print(err)
        except Exception as err:
            print("ERROR: ", err)
            raise NotifyException(
                f"{err}"
            ) from err

    async def get_sticker(self, sticker_id):
        if isinstance(sticker_id, dict):  # getting from an sticker_set
            name = sticker_id["set"]
            em = sticker_id["emoji"]
            print(emoji.emojize(em))
            if isinstance(em, str) and em.startswith(":"):
                em = emoji.emojize(em)
            try:
                sticker_set = await self._bot.get_sticker_set(name)
                self.logger.debug(
                    f"Sticker Set Found: {sticker_set!r}"
                )
                st = [x for x in sticker_set.stickers if x.emoji == em]
                print('STICKER', st, type(st))
                sticker = st[0].file_id
                return sticker
            except Exception as err:
                self.logger.warning(
                    f"Sticker finder error: {err}"
                )
                return None
        else:
            return "CAACAgEAAxkBAAIuOWMze9CZzg6cQaEulHqjrcRCvBh2AAK_AgACJjFuAVdTX0Nu_LoxKgQ"

    async def send_sticker(self, sticker: Union[str, Any], **kwargs):
        chat_id = self.get_chat()
        sticker = await self.get_sticker(sticker)
        try:
            response = await self._bot.send_sticker(chat_id, sticker=sticker, **kwargs)
            # print(response) # TODO: make the processing of response
            return response
        except TelegramUnauthorizedError as err:
            # remove update.message.chat_id from conversation list
            print(err)
        except TelegramNotFound as err:
            # the chat_id of a group has changed, use e.new_chat_id instead
            print(err)
        except TelegramBadRequest as err:
            # handle malformed requests - read more below!
            print(err)
        except TelegramNetworkError as err:
            # handle slow connection problems
            print(err)
        except TelegramAPIError as err:
            # handle all other telegram related errors
            print(err)
        except Exception as err:
            print("ERROR: ", err)
            raise NotifyException(
                f"{err}"
            ) from err

    def convert_to_mp4(self, video: Union[str, PurePath, Any], format: str = 'libx264') -> Any:
        clip = VideoFileClip(str(video))
        output_file = Path().joinpath(video.parent, video.stem + ".mp4")
        clip.write_videofile(str(output_file), codec=format)
        return output_file

    async def get_media(self, media: Union[str, PurePath, Any]) -> Any:
        if isinstance(media, PurePath):  # Path to a File:
            if media.exists():
                if media.suffix == ".webm":
                    # its a webm video, convert to mp4
                    media = self.convert_to_mp4(media)
                    return FSInputFile(media, filename=media.name)
                return FSInputFile(media, filename=media.name)
            else:
                raise FileNotFoundError(
                    f"Telegram Bot: file {media} doesn't exists."
                )
        elif isinstance(media, str):
            if media.startswith("http"):
                # its an URL
                return URLInputFile(media)
            return FSInputFile(media)
        elif isinstance(media, BytesIO):
            media.seek(0)
            return BufferedInputFile(media)
        else:
            return FSInputFile(media)

    async def send_video(self, video: Union[str, Any], **kwargs):
        chat_id = self.get_chat()
        media = await self.get_media(video)
        try:
            response = await self._bot.send_video(chat_id, video=media, **kwargs)
            # print(response) # TODO: make the processing of response
            return response
        except TelegramUnauthorizedError as err:
            # remove update.message.chat_id from conversation list
            print(err)
        except TelegramNotFound as err:
            # the chat_id of a group has changed, use e.new_chat_id instead
            print(err)
        except TelegramBadRequest as err:
            # handle malformed requests - read more below!
            print(err)
        except TelegramNetworkError as err:
            # handle slow connection problems
            print(err)
        except TelegramAPIError as err:
            # handle all other telegram related errors
            print(err)
        except Exception as err:
            print("ERROR: ", err)
            raise NotifyException(
                f"{err}"
            ) from err

    async def send_audio(self, audio: Union[str, PurePath, Any], **kwargs):
        chat_id = self.get_chat()
        sound = await self.get_media(audio)
        try:
            response = await self._bot.send_audio(chat_id, audio=sound, **kwargs)
            # print(response) # TODO: make the processing of response
            return response
        except TelegramUnauthorizedError as err:
            # remove update.message.chat_id from conversation list
            print(err)
        except TelegramNotFound as err:
            # the chat_id of a group has changed, use e.new_chat_id instead
            print(err)
        except TelegramBadRequest as err:
            # handle malformed requests - read more below!
            print(err)
        except TelegramNetworkError as err:
            # handle slow connection problems
            print(err)
        except TelegramAPIError as err:
            # handle all other telegram related errors
            print(err)
        except Exception as err:
            print("ERROR: ", err)
            raise NotifyException(
                f"{err}"
            ) from err
