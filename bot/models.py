from pydantic import BaseModel


class TelegramUser(BaseModel):
    user_id: int
    messages: list[str]
    context_length: int = 2
