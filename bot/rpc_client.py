import asyncio
import uuid
from typing import MutableMapping
import os
from dotenv import load_dotenv

from aio_pika import Message, connect
from aio_pika.abc import (
    AbstractChannel,
    AbstractConnection,
    AbstractIncomingMessage,
    AbstractQueue,
)

load_dotenv()
RABBITMQ_CONNECTION_STRING = os.environ.get("RABBITMQ_CONNECTION_STRING")


class DiloGPTRpcClient:
    connection: AbstractConnection
    channel: AbstractChannel
    callback_queue: AbstractQueue
    loop: asyncio.AbstractEventLoop

    def __init__(self, connection_string: str) -> None:
        self.futures: MutableMapping[str, asyncio.Future] = {}
        self.connection_string = connection_string
        self.connection = None

    async def connect(self) -> "DiloGPTRpcClient":
        self.connection = await connect(
            self.connection_string,
        )
        self.channel = await self.connection.channel()
        self.callback_queue = await self.channel.declare_queue(exclusive=True)
        await self.callback_queue.consume(self.on_response, no_ack=True)

        return self

    async def on_response(self, message: AbstractIncomingMessage) -> None:
        if message.correlation_id is None:
            print(f"Bad message {message!r}")
            return

        future: asyncio.Future = self.futures.pop(message.correlation_id)
        future.set_result(message.body)

    async def call(self, messages: list[str]) -> str:
        if not self.connection:
            await self.connect()

        correlation_id = str(uuid.uuid4())
        future = asyncio.Future()

        self.futures[correlation_id] = future

        await self.channel.default_exchange.publish(
            Message(
                "<:>".join(messages).encode(),
                content_type="text/plain",
                correlation_id=correlation_id,
                reply_to=self.callback_queue.name,
            ),
            routing_key="rpc_queue",
        )

        return (await future).decode()


async def main() -> None:
    dialogpt = DiloGPTRpcClient(RABBITMQ_CONNECTION_STRING)
    print(' [x] Requesting model(["Привет, как твои дела?"])')
    response = await dialogpt.call(
        [
            "Привет, как твои дела?",
        ]
    )
    print(f" [.] Got {response!r}")


if __name__ == "__main__":
    asyncio.run(main())
