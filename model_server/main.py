import asyncio
import logging
import os
import random
from aiormq import AMQPConnectionError
from dotenv import load_dotenv

from aio_pika import Message, connect
from aio_pika.abc import AbstractIncomingMessage

from predictor import Predictor


load_dotenv()
RABBITMQ_CONNECTION_STRING = os.environ.get("RABBITMQ_CONNECTION_STRING")
MODEL_DIR = os.environ.get("MODEL_DIR")

pred = Predictor(MODEL_DIR)


async def main() -> None:
    # Perform connection
    connection = None
    for _ in range(10):
        try:
            connection = await connect(RABBITMQ_CONNECTION_STRING)
            break
        except AMQPConnectionError:
            print("Trying to reconnect to rabbitmq, waiting 5 seconds")
            await asyncio.sleep(5)

    if not connection:
        print("Failed to connect")
        return
    print("Connected to rabbitmq")

    # Creating a channel
    channel = await connection.channel()
    exchange = channel.default_exchange

    # Declaring queue
    queue = await channel.declare_queue("rpc_queue")

    print(" [x] Awaiting RPC requests")

    # Start listening the queue with name 'hello'
    async with queue.iterator() as qiterator:
        message: AbstractIncomingMessage
        async for message in qiterator:
            try:
                async with message.process(requeue=False):
                    assert message.reply_to is not None

                    messages = message.body.decode().split("<:>")

                    print(f" [.] Calling model({pred.add_tokens(messages)})")
                    response = random.choice(pred.predict(messages)).encode()

                    await exchange.publish(
                        Message(
                            body=response,
                            correlation_id=message.correlation_id,
                        ),
                        routing_key=message.reply_to,
                    )
                    print("Request complete")
            except Exception:
                logging.exception("Processing error for message %r", message)


if __name__ == "__main__":
    print(RABBITMQ_CONNECTION_STRING)
    asyncio.run(main())
