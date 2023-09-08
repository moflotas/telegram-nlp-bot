from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatAction, ParseMode
import os
from dotenv import load_dotenv

import asyncio
import random

from motor.motor_asyncio import AsyncIOMotorClient
from rpc_client import DiloGPTRpcClient
import threading

from models import TelegramUser

load_dotenv()

API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
# BOT_TOKEN = os.environ.get("BOT_TOKEN")
DB_CONNECTION_STRING = os.environ.get("DB_CONNECTION_STRING")
RABBITMQ_CONNECTION_STRING = os.environ.get("RABBITMQ_CONNECTION_STRING")
PREFIX = os.environ.get("PREFIX", "Скажи,")

# uncomment bot_token for it to work as a usual bot, not as userbot
app = Client(
    "moflotas",
    api_id=API_ID,
    api_hash=API_HASH,
    # bot_token=BOT_TOKEN,
)


db_client = AsyncIOMotorClient(DB_CONNECTION_STRING)
db = db_client["telegram"]
dialogpt = DiloGPTRpcClient(RABBITMQ_CONNECTION_STRING)
with open("thinking_answers.txt") as f:
    thinking_answers = f.readlines()


# for bot not to be flooded with too many requests
is_responding = {}
lock = threading.Lock()


@app.on_message(filters.private & filters.command("help"))
async def help_command(client: Client, message: Message) -> None:
    # no need for lock, since help can be always provided
    try:
        await client.send_message(
            message.chat.id,
            (
                "Личный помощник аккаунта @moflotas\n"
                "<code>/help</code> - вывести это сообщение\n"
                "<code>/delete_history</code> - очистить контекст <s>если автоответчик несёт чушь</s>\n"
                "<code>/set_context_length &ltNUMBER&gt</code> - установить длину контекста (рекомендуется не больше 3)"
            ),
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        # if there was some problem with database or telegram
        print(e)


@app.on_message(filters.private & filters.command("set_context_length"))
async def set_context_length_command(client: Client, message: Message) -> None:
    # locking the lock in order to ignore flood from user
    with lock:
        if (
            message.from_user.id in is_responding
            and is_responding[message.from_user.id]
        ):
            return
        is_responding[message.from_user.id] = True

    try:
        if len(message.command) != 2:
            await client.send_message(message.chat.id, "Неправильно введена команда")
            raise Exception("Wrong command")

        try:
            context_length = int(message.command[1])
        except ValueError:
            await client.send_message(message.chat.id, "Неправильно введена команда")
            raise Exception("Wrong command")

        # to emulate user-like behaviour
        await client.send_chat_action(
            chat_id=message.chat.id,
            action=ChatAction.PLAYING,
        )
        await db.users.update_one(
            {"user_id": message.from_user.id},
            {"$set": {"context_length": context_length}},
        )
        await client.send_message(message.chat.id, "Длина контекст изменена")
    except Exception as e:
        # if there was some problem with database or telegram
        print(e)
    finally:
        # in any was we should release the lock, otherwise the user will have no chance of writing to bot ever again
        with lock:
            is_responding[message.from_user.id] = False


@app.on_message(filters.private & filters.command("delete_history"))
async def delete_history_command(client: Client, message: Message) -> None:
    # locking the lock in order to ignore flood from user
    with lock:
        if (
            message.from_user.id in is_responding
            and is_responding[message.from_user.id]
        ):
            return
        is_responding[message.from_user.id] = True

    try:
        # to emulate user-like behaviour
        await client.send_chat_action(
            chat_id=message.chat.id,
            action=ChatAction.PLAYING,
        )
        await db.users.delete_one({"user_id": message.from_user.id})
        await client.send_message(message.chat.id, "Контекст очищен")
    except Exception as e:
        # if there was some problem with database or telegram
        print(e)
    finally:
        # in any was we should release the lock, otherwise the user will have no chance of writing to bot ever again
        with lock:
            is_responding[message.from_user.id] = False


@app.on_message(filters.private & filters.text & filters.regex(f"{PREFIX}.*"))
async def message_handler(client: Client, message: Message) -> None:
    with lock:
        if (
            message.from_user.id in is_responding
            and is_responding[message.from_user.id]
        ):
            return
        is_responding[message.from_user.id] = True

    try:
        await client.send_chat_action(
            message.chat.id,
            ChatAction.TYPING,
        )
        bot_message = await client.send_message(
            message.chat.id,
            text=random.choice(thinking_answers),
            reply_to_message_id=message.id,
        )

        await client.send_chat_action(
            message.chat.id,
            ChatAction.TYPING,
        )
        user = await db.users.find_one(
            {"user_id": message.from_user.id},
        )

        previous_context = []

        if user:
            model_user = TelegramUser(**user)
            previous_context.extend(model_user.messages[-model_user.context_length :])

        answer = await dialogpt.call(
            previous_context + [message.text.removeprefix(PREFIX).strip()],
        )

        if not user:
            db.users.insert_one(
                TelegramUser(
                    user_id=message.from_user.id,
                    messages=[],
                ).model_dump()
            )

        await db.users.update_one(
            {"user_id": message.from_user.id},
            {
                "$push": {
                    "messages": {
                        "$each": [
                            message.text.removeprefix(PREFIX).strip(),
                            str(answer),
                        ]
                    }
                }
            },
        )

        await client.send_message(
            bot_message.chat.id,
            answer,
            reply_to_message_id=bot_message.id,
        )
    except Exception as e:
        print(e)
    finally:
        with lock:
            is_responding[message.from_user.id] = False


if __name__ == "__main__":
    app.run()
