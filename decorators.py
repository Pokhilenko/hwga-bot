"""Decorators for the bot."""

from functools import wraps
from db import set_chat_name

def update_chat_name_decorator(func):
    """Decorator to update the chat name in the database before executing a command."""
    @wraps(func)
    async def wrapper(update, context, *args, **kwargs):
        """Wrapper function that updates the chat name."""
        chat_id = str(update.effective_chat.id)
        chat_name = update.effective_chat.title
        if chat_name:
            await set_chat_name(chat_id, chat_name)
        elif update.effective_chat.type == "private":
            user = update.effective_user
            user_name = f"ЛС: {user.first_name}" + (
                f" {user.last_name}" if user.last_name else ""
            )
            await set_chat_name(chat_id, user_name)
        return await func(update, context, *args, **kwargs)
    return wrapper