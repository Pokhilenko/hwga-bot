import asyncio
import logging
import random
from datetime import datetime, timedelta
import os

from telegram import (
    BotCommand,
    BotCommandScopeDefault,
    BotCommandScopeChat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.error import BadRequest

import db
import scheduler
import web_server
import steam
from poll_state import poll_state
import config
from exceptions import DatabaseError, SteamApiError
from decorators import update_chat_name_decorator

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


async def send_message(context, chat_id, user_id, text, reply_markup=None):
    """Sends a message to a user, trying private chat first."""
    try:
        await context.bot.send_message(
            chat_id=user_id, text=text, reply_markup=reply_markup
        )
        if chat_id != user_id:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Я отправил тебе информацию в личные сообщения, @{context.user_data.get('username')}",
            )
    except BadRequest:
        await context.bot.send_message(
            chat_id=chat_id, text=text, reply_markup=reply_markup
        )


@update_chat_name_decorator
async def start(update, context):
    """Send a message when the command /start is issued."""
    chat_id = str(update.effective_chat.id)

    try:
        # Register this chat for daily polls
        poll_state.register_chat(chat_id)

        # Store user info
        await db.store_user_info(update.effective_user)

        await update.message.reply_text(config.MSG_WELCOME)
    except DatabaseError as e:
        logger.error(f"Database error in start command: {e}")
        await update.message.reply_text("Произошла ошибка базы данных. Попробуйте позже.")


@update_chat_name_decorator
async def poll_now_command(update, context):
    """Start a new poll manually."""
    chat_id = str(update.effective_chat.id)
    user = update.effective_user

    try:
        # Check if there's already an active poll
        if poll_state.is_active(chat_id):
            await update.message.reply_text(config.MSG_POLL_ALREADY_ACTIVE)
            return

        # Leading message for manual poll
        message = config.MSG_MANUAL_POLL_INVITATION.format(user_name=user.first_name)
        await send_poll(chat_id, context, message, manual=True)
    except DatabaseError as e:
        logger.error(f"Database error in poll_now_command: {e}")
        await update.message.reply_text("Произошла ошибка базы данных. Попробуйте позже.")


@update_chat_name_decorator
async def stop_poll(update, context):
    """Manually stop the current poll."""
    chat_id = str(update.effective_chat.id)

    try:
        if not poll_state.is_active(chat_id):
            await update.message.reply_text(config.MSG_NO_ACTIVE_POLL)
            return

        poll_data = poll_state.get_poll_data(chat_id)

        try:
            # Try to stop the poll in Telegram
            await context.bot.stop_poll(chat_id=chat_id, message_id=poll_data["message_id"])
        except BadRequest:
            # Poll might be already closed
            pass

        # Process the results
        await process_poll_results(chat_id, context)
    except DatabaseError as e:
        logger.error(f"Database error in stop_poll command: {e}")
        await update.message.reply_text("Произошла ошибка базы данных. Попробуйте позже.")


@update_chat_name_decorator
async def status_command(update, context):
    """Check the status of the current poll."""
    chat_id = str(update.effective_chat.id)

    try:
        if not poll_state.is_active(chat_id):
            await update.message.reply_text(config.MSG_NO_ACTIVE_POLL)
            return

        poll_data = poll_state.get_poll_data(chat_id)
        votes = poll_data["votes"]

        # Count votes by option
        vote_counts = [0] * len(config.POLL_OPTIONS)
        for vote in votes.values():
            option_index = vote["option"]
            vote_counts[option_index] += 1

        # Format status message
        status_message = f"{config.MSG_POLL_STATUS}\n"
        for i, option in enumerate(config.POLL_OPTIONS):
            status_message += f"• {option}: {vote_counts[i]} голосов\n"

        # Add who has voted
        status_message += f"\n{config.MSG_VOTED}\n"
        for vote in votes.values():
            user = vote["user"]
            option = config.POLL_OPTIONS[vote["option"]]
            status_message += f"• {user.first_name}: {option}\n"

        # Add who hasn't voted yet
        non_voted = poll_data["all_users"] - poll_data["voted_users"]
        if non_voted:
            status_message += f"\n{config.MSG_NOT_VOTED_YET}\n"
            for user_id in non_voted:
                # We don't have user names for those who haven't voted yet
                status_message += f"• User ID: {user_id}\n"

        await update.message.reply_text(status_message)
    except DatabaseError as e:
        logger.error(f"Database error in status_command: {e}")
        await update.message.reply_text("Произошла ошибка базы данных. Попробуйте позже.")


@update_chat_name_decorator
async def stats_command(update, context):
    """Display poll statistics."""
    chat_id = str(update.effective_chat.id)

    try:
        stats = await db.get_poll_stats(chat_id, config.POLL_OPTIONS)

        total_polls = stats["total_polls"]
        most_popular_result = stats["most_popular"]
        times = stats["times"]

        most_popular_option = "Нет данных"
        if most_popular_result:
            option_index, count = most_popular_result
            most_popular_option = config.MSG_MOST_POPULAR_OPTION.format(
                option=config.POLL_OPTIONS[option_index], count=count
            )

        avg_time = "Нет данных"
        if times:
            # Convert times to minutes since midnight
            minutes_list = []
            for (time_str,) in times:
                hour, minute = map(int, time_str.split(":"))
                minutes_since_midnight = hour * 60 + minute
                minutes_list.append(minutes_since_midnight)

            # Calculate average minutes
            avg_minutes = sum(minutes_list) / len(minutes_list)

            # Convert back to hours:minutes
            avg_hour = int(avg_minutes // 60)
            avg_minute = int(avg_minutes % 60)
            avg_time = f"{avg_hour:02d}:{avg_minute:02d} (GMT+6)"

        # Получаем URL для веб-страницы статистики
        stats_url = web_server.get_stats_url(chat_id)

        # Логируем URL для отладки
        logger.info(f"Stats URL for chat {chat_id}: {stats_url}")

        # Базовый текст сообщения без ссылки
        stats_message = f"{config.MSG_STATS_TITLE}\n\n"
        stats_message += f'{config.MSG_TOTAL_POLLS.format(total_polls=total_polls)}\n'
        stats_message += f'{most_popular_option}\n'
        stats_message += f'{config.MSG_AVG_POLL_TIME.format(time=avg_time)}\n\n'

        # Определяем, локальный ли это адрес
        is_localhost = "localhost" in stats_url or "127.0.0.1" in stats_url

        if is_localhost:
            # Для локальных URL используем обычный текст
            stats_message += f'{config.MSG_STATS_URL.format(url=stats_url)}\n\n'
            stats_message += config.MSG_STATS_URL_LOCAL_WARNING

            # Отправляем сообщение без кнопки
            await update.message.reply_text(stats_message)
        else:
            # Для рабочих URL используем inline кнопку
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup

            stats_message += config.MSG_STATS_URL_BUTTON

            # Создаем inline кнопку с ссылкой
            keyboard = [
                [InlineKeyboardButton("Открыть детальную статистику", url=stats_url)]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Отправляем сообщение с кнопкой
            await update.message.reply_text(stats_message, reply_markup=reply_markup)

    except (BadRequest, DatabaseError) as e:
        logger.error(f"Error in stats_command: {e}")
        await update.message.reply_text("Произошла ошибка. Попробуйте позже.")


@update_chat_name_decorator
async def set_poll_time_command(update, context):
    """Set custom poll time for a chat."""
    chat_id = str(update.effective_chat.id)

    try:
        args = context.args

        if not args or len(args) < 1:
            await update.message.reply_text(config.MSG_SET_POLL_TIME_PROMPT)
            return

        # Join all args in case there are spaces
        time_str = " ".join(args)

        # Parse and convert the time string to UTC
        utc_time_str = await scheduler.parse_time_string(time_str)

        if not utc_time_str:
            await update.message.reply_text(config.MSG_INVALID_TIME_FORMAT)
            return

        # Save to database
        success = await db.set_poll_time(chat_id, utc_time_str)

        if success:
            # Convert UTC back to GMT+6 for display
            hour, minute = map(int, utc_time_str.split(":"))
            dt = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
            dt += timedelta(hours=6)  # UTC to GMT+6
            gmt6_time = f"{dt.hour:02d}:{dt.minute:02d}"

            await update.message.reply_text(
                config.MSG_POLL_TIME_SET.format(time=gmt6_time)
            )

            # Reschedule the poll
            success = await scheduler.reschedule_poll_for_chat(
                context.job_queue, chat_id, send_poll
            )

            if not success:
                await update.message.reply_text(config.MSG_POLL_RESCHEDULE_ERROR)
        else:
            await update.message.reply_text(config.MSG_POLL_TIME_SAVE_ERROR)
    except DatabaseError as e:
        logger.error(f"Database error in set_poll_time_command: {e}")
        await update.message.reply_text("Произошла ошибка базы данных. Попробуйте позже.")


@update_chat_name_decorator
async def get_poll_time_command(update, context):
    """Display the currently configured poll time."""
    chat_id = str(update.effective_chat.id)

    try:
        poll_time_str = await db.get_poll_time(chat_id)

        # Convert UTC time back to GMT+6 for display
        hour, minute = map(int, poll_time_str.split(":"))
        dt = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
        dt += timedelta(hours=6)
        gmt6_time = f"{dt.hour:02d}:{dt.minute:02d}"

        await update.message.reply_text(
            config.MSG_CURRENT_POLL_TIME.format(time=gmt6_time)
        )
    except DatabaseError as e:
        logger.error(f"Database error in get_poll_time_command: {e}")
        await update.message.reply_text("Произошла ошибка базы данных. Попробуйте позже.")


@update_chat_name_decorator
async def link_steam_command(update, context):
    """Handler for the command to link a Steam ID via OAuth"""
    user = update.effective_user
    chat = update.effective_chat
    chat_id = str(chat.id)

    try:
        if not await db.is_user_registered(user.id):
            await db.register_user(user)

        # Check if a Steam ID is already linked to this chat
        is_linked = await db.is_steam_id_linked_to_chat(user.id, chat_id)

        if is_linked:
            # Get the chat name
            chat_name = await db.get_chat_name_by_id(chat_id) or "этом чате"

            # Send a message to the user's private chat
            await send_message(
                context,
                chat_id,
                user.id,
                config.MSG_STEAM_ID_ALREADY_LINKED.format(chat_name=chat_name),
            )
            return

        # Get the URL for authorization via Steam OpenID with the chat ID
        auth_url = web_server.get_steam_auth_url(user.id, chat_id)

        # Create a message with an inline button for authorization
        keyboard = [[InlineKeyboardButton("Войти через Steam", url=auth_url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Send a message with instructions to either the private chat or the group chat
        await send_message(
            context,
            chat_id,
            user.id,
            config.MSG_STEAM_LINK_PROMPT,
            reply_markup=reply_markup,
        )

        logger.info(
            f"User {user.id} ({user.username}) requested Steam authentication link for chat {chat_id}"
        )
    except DatabaseError as e:
        logger.error(f"Database error in link_steam_command: {e}")
        await update.message.reply_text("Произошла ошибка базы данных. Попробуйте позже.")


@update_chat_name_decorator
async def unlink_steam_command(update, context):
    """Unlinks a Steam ID from a user's account."""
    user = update.effective_user
    user_id = user.id
    chat = update.effective_chat
    chat_id = str(chat.id)

    try:
        # Get user information
        user_info = await db.get_user_info(user_id)

        # Check if the Steam ID is linked to this chat
        is_linked = await db.is_steam_id_linked_to_chat(user_id, chat_id)

        if not is_linked:
            await send_message(
                context, chat_id, user_id, config.MSG_STEAM_ID_NOT_LINKED
            )
            return

        if not user_info or not user_info["steam_id"]:
            await send_message(
                context, chat_id, user_id, config.MSG_STEAM_ID_NOT_LINKED
            )
            return

        # Получаем название чата
        chat_name = await db.get_chat_name_by_id(chat_id) or "этого чата"

        # Show information about the current Steam account
        steam_id = user_info["steam_id"]

        # Create buttons to confirm unlinking
        keyboard = [
            [
                InlineKeyboardButton(
                    "Да, отвязать", callback_data=f"unlink_confirm:{user_id}:{chat_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "Отмена", callback_data=f"unlink_cancel:{user_id}:{chat_id}"
                )
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Get the Steam API key from environment variables
        steam_api_key = os.environ.get("STEAM_API_KEY")

        message_text = ""

        if steam_api_key:
            # Get profile information for display
            profile_data = await steam.verify_steam_id(steam_id, steam_api_key)

            if profile_data:
                steam_name = profile_data["username"]
                profile_url = profile_data["profile_url"]

                message_text = config.MSG_UNLINK_STEAM_CONFIRM.format(
                    chat_name=chat_name, steam_id=steam_id, steam_name=steam_name
                )

                # Add a button to go to the profile
                keyboard.insert(
                    0, [InlineKeyboardButton("Просмотреть профиль", url=profile_url)]
                )
                reply_markup = InlineKeyboardMarkup(keyboard)
            else:
                message_text = config.MSG_UNLINK_STEAM_CONFIRM_NO_PROFILE.format(
                    steam_id=steam_id, chat_name=chat_name
                )
        else:
            message_text = config.MSG_UNLINK_STEAM_CONFIRM_NO_PROFILE.format(
                steam_id=steam_id, chat_name=chat_name
            )

        # Send a confirmation message to the private chat or the group chat
        await send_message(
            context, chat_id, user_id, message_text, reply_markup=reply_markup
        )

        logger.info(
            f"User {user.first_name} ({user_id}) requested to unlink Steam ID {steam_id} from chat {chat_id}"
        )
    except (DatabaseError, SteamApiError) as e:
        logger.error(f"Error in unlink_steam_command: {e}")
        await update.message.reply_text("Произошла ошибка. Попробуйте позже.")


@update_chat_name_decorator
async def handle_unlink_steam_confirm(update, context):
    """Handles the confirmation of unlinking a Steam ID."""
    query = update.callback_query
    await query.answer()

    callback_data = query.data
    parts = callback_data.split(":")
    user_id = int(parts[1])
    chat_id = parts[2] if len(parts) > 2 else None
    current_user_id = query.from_user.id

    # Check that the button was pressed by the user who requested the unlinking
    if user_id != current_user_id:
        await query.edit_message_text(
            "Ошибка: эта кнопка предназначена для другого пользователя."
        )
        return

    try:
        # Получаем название чата
        chat_name = (
            await db.get_chat_name_by_id(chat_id) if chat_id else "неизвестного чата"
        )

        # Unlink the Steam ID
        success = await db.remove_user_steam_id(user_id, chat_id)

        if success:
            await query.edit_message_text(
                config.MSG_UNLINK_STEAM_SUCCESS.format(chat_name=chat_name),
                parse_mode="HTML",
            )
            logger.info(
                f"User {query.from_user.first_name} ({user_id}) unlinked their Steam ID from chat {chat_id}"
            )
        else:
            await query.edit_message_text(config.MSG_UNLINK_STEAM_ERROR)
            logger.error(f"Error unlinking Steam ID for user {user_id} from chat {chat_id}")
    except DatabaseError as e:
        logger.error(f"Database error in handle_unlink_steam_confirm: {e}")
        await query.edit_message_text(config.MSG_UNLINK_STEAM_ERROR)


@update_chat_name_decorator
async def handle_unlink_steam_cancel(update, context):
    """Handles the cancellation of unlinking a Steam ID."""
    query = update.callback_query
    await query.answer()

    callback_data = query.data
    parts = callback_data.split(":")
    user_id = parts[1]
    chat_id = parts[2] if len(parts) > 2 else None

    await query.edit_message_text(config.MSG_UNLINK_STEAM_CANCEL)

    logger.info(
        f"User {query.from_user.first_name} ({user_id}) canceled unlinking Steam ID from chat {chat_id}"
    )


@update_chat_name_decorator
async def handle_poll_answer(update, context):
    """Handle when a user answers the poll."""
    answer = update.poll_answer
    poll_id = answer.poll_id
    user = update.effective_user
    selected_option = answer.option_ids[0] if answer.option_ids else None

    try:
        # Record this vote
        if selected_option is not None:
            await poll_state.add_vote(poll_id, user, selected_option)

        # Check if the chat is private
        for chat_id, poll_data in list(poll_state.active_polls.items()):
            if poll_data["poll_id"] == poll_id:
                # Get the numeric chat ID
                numeric_chat_id = int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id

                # Private chats have a positive ID
                is_personal_chat = isinstance(numeric_chat_id, int) and numeric_chat_id > 0

                # If it's a private chat, don't end the poll immediately after a single vote
                if is_personal_chat:
                    logger.info(f"Голос в личном чате {chat_id}, ожидаем таймаута")
                    return

                # For group chats, end the poll if everyone has voted
                # Avoid ending when only one participant is known (usually the administrator)
                if len(poll_data["all_users"]) > 1 and poll_data["all_users"].issubset(
                    poll_data["voted_users"]
                ):
                    logger.info(
                        f"Все пользователи проголосовали в чате {chat_id}, завершаем опрос"
                    )
                    await process_poll_results(chat_id, context)
                break
    except DatabaseError as e:
        logger.error(f"Database error in handle_poll_answer: {e}")


async def send_poll(chat_id, context, message, manual=False):
    """Send a poll to the specified chat."""
    try:
        # If chat_id is a string with a number, convert it to int for the Telegram API
        numeric_chat_id = int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id

        # Send the leading message
        await context.bot.send_message(chat_id=numeric_chat_id, text=message)

        # Send the actual poll
        poll_message = await context.bot.send_poll(
            chat_id=numeric_chat_id,
            question=config.POLL_QUESTION,
            options=config.POLL_OPTIONS,
            is_anonymous=False,
        )

        # Store poll information
        poll_id = poll_message.poll.id
        message_id = poll_message.message_id
        trigger_type = "manual" if manual else "scheduled"
        await poll_state.create_poll(chat_id, poll_id, message_id, trigger_type)

        # Get known chat members from DB
        known_users = await db.get_known_chat_users(chat_id)
        for uid in known_users:
            poll_state.add_user_to_chat(chat_id, uid)

        # Add administrators as a fallback
        try:
            chat_members = await context.bot.get_chat_administrators(numeric_chat_id)
            for member in chat_members:
                if not member.user.is_bot:
                    poll_state.add_user_to_chat(chat_id, member.user.id)
        except BadRequest:
            # This might fail in some chat types
            logger.warning(f"Couldn't get chat members for {chat_id}")

        # Schedule the first reminder (after 10 minutes)
        context.application.create_task(send_reminder(chat_id, context, 10 * 60))

        # Schedule poll closing (after 20 minutes)
        poll_timeout = context.application.create_task(
            close_poll_after_timeout(chat_id, context, 20 * 60)
        )

        # Save the final task (it will cancel and replace any previous tasks)
        poll_state.set_task(chat_id, poll_timeout)
    except (BadRequest, DatabaseError) as e:
        logger.error(f"Error in send_poll: {e}", exc_info=True)


@update_chat_name_decorator
async def send_reminder(chat_id, context, delay):
    """Send a reminder to users who haven't voted."""
    await asyncio.sleep(delay)

    try:
        # Check if poll is still active
        if not poll_state.is_active(chat_id):
            return

        poll_data = poll_state.get_poll_data(chat_id)
        poll_data["first_ping_sent"] = True

        # Get users who haven't voted
        non_voted = poll_data["all_users"] - poll_data["voted_users"]
        if not non_voted:
            return

        # Format the ping message with usernames
        ping_message = ""
        for user_id in non_voted:
            # Get user information из базы данных
            user_info = await db.get_user_info(user_id)
            if user_info and user_info["username"]:
                # Если у пользователя есть username, используем его для упоминания
                ping_message += f"@{user_info['username']} "
            elif user_info and user_info["first_name"]:
                # Если нет username, то используем имя
                ping_message += f"{user_info['first_name']} "
            else:
                # Если нет информации о пользователе, используем ID
                ping_message += f"ID:{user_id} "

        if ping_message:
            await context.bot.send_message(
                chat_id=chat_id, text=config.MSG_REMINDER.format(users=ping_message)
            )
    except (BadRequest, DatabaseError) as e:
        logger.error(f"Error in send_reminder: {e}")


@update_chat_name_decorator
async def close_poll_after_timeout(chat_id, context, delay):
    """Close the poll after the specified delay."""
    await asyncio.sleep(delay)

    try:
        # Check if poll is still active
        if not poll_state.is_active(chat_id):
            return

        poll_data = poll_state.get_poll_data(chat_id)

        try:
            # Stop the poll in Telegram
            await context.bot.stop_poll(chat_id=chat_id, message_id=poll_data["message_id"])
        except BadRequest:
            # Poll might already be closed
            pass

        # Process the results
        await process_poll_results(chat_id, context)
    except (BadRequest, DatabaseError) as e:
        logger.error(f"Error in close_poll_after_timeout: {e}")


@update_chat_name_decorator
async def process_poll_results(chat_id, context):
    """Process the poll results and send the appropriate message."""
    try:
        if not poll_state.is_active(chat_id):
            return

        poll_data = poll_state.get_poll_data(chat_id)
        votes = poll_data["votes"]

        # Group users by their vote category
        categories = {
            "accepted": [],
            "declined": [],
            "deferred": [],
        }

        for vote in votes.values():
            user = vote["user"]
            option = vote["option"]

            # Determine which category this option belongs to
            for category, indices in config.CATEGORY_MAPPING.items():
                if option in indices:
                    categories[category].append(user.first_name)
                    break

        # Determine which option was selected for the deferred category to set the right delay
        deferred_delay = None
        if categories["deferred"]:
            option_5_selected = False
            for vote in votes.values():
                if vote["option"] == 4:  # Index 4 is for "Полчасика и буду пасасэо"
                    option_5_selected = True
                    break

            if option_5_selected:
                deferred_delay = 30
            else:
                deferred_delay = random.randint(5, 10)

        # Construct the result message
        if (
            categories["accepted"]
            and not categories["declined"]
            and not categories["deferred"]
        ):
            result_message = config.MSG_POLL_RESULT_ALL_ACCEPTED
        elif (
            categories["declined"]
            and not categories["accepted"]
            and not categories["deferred"]
        ):
            result_message = config.MSG_POLL_RESULT_ALL_DECLINED
        elif (
            not categories["accepted"]
            and not categories["declined"]
            and not categories["deferred"]
        ):
            result_message = config.MSG_POLL_RESULT_ALL_DECLINED
        elif (
            not categories["accepted"]
            and not categories["declined"]
            and categories["deferred"]
        ):
            result_message = config.MSG_POLL_RESULT_ALL_DEFERRED.format(
                delay=deferred_delay
            )
        else:
            result_message = ""
            if categories["accepted"]:
                result_message += config.MSG_POLL_RESULT_ACCEPTED.format(
                    users=", ".join(categories["accepted"])
                )
            if categories["declined"]:
                result_message += config.MSG_POLL_RESULT_DECLINED.format(
                    users=", ".join(categories["declined"])
                )
            if categories["deferred"]:
                result_message += config.MSG_POLL_RESULT_DEFERRED.format(
                    users=", ".join(categories["deferred"])
                )

        # Add info about users who didn't vote
        non_voted = poll_data["all_users"] - poll_data["voted_users"]
        if non_voted and poll_data["first_ping_sent"]:
            # Get the names of users who didn't vote
            non_voted_names = []
            for user_id in non_voted:
                user_info = await db.get_user_info(user_id)
                if user_info:
                    if user_info["username"]:
                        non_voted_names.append(f"@{user_info['username']}")
                    elif user_info["first_name"]:
                        non_voted_names.append(user_info["first_name"])
                    else:
                        non_voted_names.append(f"ID:{user_id}")
                else:
                    non_voted_names.append(f"ID:{user_id}")

            result_message += config.MSG_POLL_RESULT_NOT_VOTED.format(
                users=", ".join(non_voted_names)
            )

        # Send result message
        await context.bot.send_message(chat_id=chat_id, text=result_message)

        # Close the poll in our state
        await poll_state.close_poll(chat_id)
    except (BadRequest, DatabaseError) as e:
        logger.error(f"Error in process_poll_results: {e}")


@update_chat_name_decorator
async def schedule_new_poll(chat_id, context, delay):
    """Schedule a new poll after the specified delay."""
    await asyncio.sleep(delay)
    await send_poll(chat_id, context, config.MSG_NEW_POLL)


async def setup_commands(application):
    """Set up bot commands to be suggested in the Telegram UI."""
    commands = [
        BotCommand("poll_now", "Начать опрос вручную"),
        BotCommand("status", "Проверить статус текущего опроса"),
        BotCommand("stop_poll", "Остановить текущий опрос"),
        BotCommand("link_steam", "Привязать Steam ID"),
        BotCommand("unlink_steam", "Отвязать Steam ID"),
        BotCommand("who_is_playing", "Показать кто играет в Dota 2"),
        BotCommand("stats", "Статистика опросов"),
        BotCommand("set_poll_time", "Установить время опроса (ЧЧ:ММ)"),
        BotCommand("get_poll_time", "Показать установленное время опроса"),
    ]

    # Set commands globally
    await application.bot.set_my_commands(commands, scope=BotCommandScopeDefault())

    # Set commands for all registered chats
    for chat_id in poll_state.registered_chats:
        try:
            await application.bot.set_my_commands(
                commands, scope=BotCommandScopeChat(chat_id=chat_id)
            )
            logger.info(f"Commands set up for chat {chat_id}")
        except Exception as e:
            logger.error(f"Failed to set commands for chat {chat_id}: {e}")

    logger.info("Bot commands have been set up")


@update_chat_name_decorator
async def who_is_playing_command(update, context):
    """Displays the status of Steam users in the current chat"""
    chat_id = str(update.effective_chat.id)

    try:
        # Send a message that the check has started
        status_message = await update.message.reply_text(
            config.MSG_WHO_IS_PLAYING_CHECKING,
            reply_to_message_id=update.message.message_id,
        )

        # Get the Steam API key
        steam_api_key = os.environ.get("STEAM_API_KEY")
        if not steam_api_key:
            await status_message.edit_text(config.MSG_STEAM_API_KEY_MISSING)
            return

        status_text = await steam.get_steam_player_statuses(chat_id, steam_api_key)
        await status_message.edit_text(status_text)

    except (BadRequest, DatabaseError, SteamApiError) as e:
        logger.error(f"Error in who_is_playing_command: {e}")
        await update.message.reply_text(
            config.MSG_WHO_IS_PLAYING_ERROR.format(error=str(e))
        )