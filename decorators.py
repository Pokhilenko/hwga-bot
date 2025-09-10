"""Decorators for the bot."""

from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from db import set_chat_name
from telegram.error import BadRequest
import logging

logger = logging.getLogger(__name__)


def update_chat_name_decorator(func):
    """Decorator to update the chat name in the database before executing a command."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        """Wrapper function that updates the chat name."""
        # The first argument could be `update` or `chat_id`.
        # The second argument is likely `context`.
        update_or_chat_id = args[0]
        context = args[1] if len(args) > 1 else None

        chat_id = None
        chat_name = None

        if isinstance(update_or_chat_id, Update):
            update = update_or_chat_id
            if update.effective_chat:
                chat_id = str(update.effective_chat.id)
                chat_name = update.effective_chat.title
                if not chat_name and update.effective_chat.type == "private":
                    user = update.effective_user
                    if user:
                        chat_name = f"ЛС: {user.first_name}" + (
                            f" {user.last_name}" if user.last_name else ""
                        )
        elif isinstance(update_or_chat_id, str):
            chat_id = update_or_chat_id
            if context and hasattr(context, "bot"):
                try:
                    chat = await context.bot.get_chat(chat_id)
                    chat_name = chat.title
                except BadRequest as e:
                    logger.warning(f"Could not get chat info for {chat_id}: {e}")

        if chat_id and chat_name:
            await set_chat_name(chat_id, chat_name)

        return await func(*args, **kwargs)

    return wrapper


def admin_only(func):
    """Decorator to check if the user is an admin in a group chat."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not update.effective_chat or update.effective_chat.type == 'private':
            # No admin check needed in private chats
            return await func(update, context, *args, **kwargs)

        user_id = update.effective_user.id
        chat_id = update.effective_chat.id

        admins = await context.bot.get_chat_administrators(chat_id)
        admin_ids = {admin.user.id for admin in admins}

        if user_id not in admin_ids:
            await update.message.reply_text("You must be an admin to use this command.")
            return

        return await func(update, context, *args, **kwargs)
    return wrapper
