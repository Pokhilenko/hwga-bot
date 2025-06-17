import asyncio
import logging
import random
import string
from datetime import datetime, timedelta
import re
import os
import ssl
import aiohttp

from telegram import BotCommand, BotCommandScopeDefault, BotCommandScopeChat, InlineKeyboardButton, InlineKeyboardMarkup, Update, LabeledPrice
from telegram.error import BadRequest
from telegram.ext import ConversationHandler, ContextTypes
from telegram.constants import ParseMode

import db
import scheduler
import web_server
import steam
from poll_state import poll_state

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
POLL_QUESTION = "Хатим сасать!?!?!"
POLL_OPTIONS = [
    "Конечно, нахуй, да!",
    "А когда не сасать?!",
    "Со вчерашнего рот болит",
    "5-10 минут и готов сасать",
    "Полчасика и буду пасасэо"
]

# Poll category mappings (0-indexed)
CATEGORY_MAPPING = {
    "accepted": [0, 1],  # Option indices for accepted category
    "declined": [2],  # Option indices for declined category
    "deferred": [3, 4]  # Option indices for deferred category
}


async def update_chat_name(update, chat_id=None):
    """Обновляет название чата в базе данных"""
    if chat_id is None:
        chat_id = str(update.effective_chat.id)
    
    chat_name = update.effective_chat.title
    if chat_name:
        await db.set_chat_name(chat_id, chat_name)
        logger.debug(f"Updated chat name: {chat_id} -> {chat_name}")
        return True
    elif update.effective_chat.type == 'private':
        # Если это личный чат, используем имя пользователя
        user = update.effective_user
        user_name = f"ЛС: {user.first_name}" + (f" {user.last_name}" if user.last_name else "")
        await db.set_chat_name(chat_id, user_name)
        logger.debug(f"Private chat name set: {chat_id} -> {user_name}")
        return True
    return False

async def start(update, context):
    """Send a message when the command /start is issued."""
    chat_id = str(update.effective_chat.id)
    
    # Обновляем название чата
    await update_chat_name(update, chat_id)

    # Register this chat for daily polls
    poll_state.register_chat(chat_id)

    # Store user info
    await db.store_user_info(update.effective_user)

    await update.message.reply_text(
        "Привет! Я бот для опросов.\n"
        "/pol_now - начать опрос вручную\n"
        "/status - проверить статус текущего опроса\n"
        "/stop_poll - остановить текущий опрос\n"
        "/link_steam - привязать Steam ID\n"
        "/unlink_steam - отвязать Steam ID\n"
        "/stats - статистика опросов\n"
        "/set_poll_time - установить время опроса (ЧЧ:ММ)\n"
        "/get_poll_time - показать установленное время опроса"
    )

async def poll_now_command(update, context):
    """Start a new poll manually."""
    chat_id = str(update.effective_chat.id)
    user = update.effective_user
    
    # Обновляем название чата
    await update_chat_name(update, chat_id)

    # Check if there's already an active poll
    if poll_state.is_active(chat_id):
        await update.message.reply_text("Опрос уже активен.")
        return

    # Leading message for manual poll
    message = f"{user.first_name} приглашает всех на посасать!"
    await send_poll(chat_id, context, message, manual=True)

async def stop_poll(update, context):
    """Manually stop the current poll."""
    chat_id = str(update.effective_chat.id)
    
    # Обновляем название чата
    await update_chat_name(update, chat_id)

    if not poll_state.is_active(chat_id):
        await update.message.reply_text("Нет активного отсоса.")
        return

    poll_data = poll_state.get_poll_data(chat_id)

    try:
        # Try to stop the poll in Telegram
        await context.bot.stop_poll(
            chat_id=chat_id,
            message_id=poll_data["message_id"]
        )
    except BadRequest:
        # Poll might be already closed
        pass

    # Process the results
    await process_poll_results(chat_id, context)

async def status_command(update, context):
    """Check the status of the current poll."""
    chat_id = str(update.effective_chat.id)
    
    # Обновляем название чата
    await update_chat_name(update, chat_id)

    if not poll_state.is_active(chat_id):
        await update.message.reply_text("Нет активного отсоса.")
        return

    poll_data = poll_state.get_poll_data(chat_id)
    votes = poll_data["votes"]

    # Count votes by option
    vote_counts = [0] * len(POLL_OPTIONS)
    for vote in votes.values():
        option_index = vote["option"]
        vote_counts[option_index] += 1

    # Format status message
    status_message = "Статус опроса:\n"
    for i, option in enumerate(POLL_OPTIONS):
        status_message += f"• {option}: {vote_counts[i]} голосов\n"

    # Add who has voted
    status_message += "\nПроголосовали:\n"
    for vote in votes.values():
        user = vote["user"]
        option = POLL_OPTIONS[vote["option"]]
        status_message += f"• {user.first_name}: {option}\n"

    # Add who hasn't voted yet
    non_voted = poll_data["all_users"] - poll_data["voted_users"]
    if non_voted:
        status_message += "\nЕще не проголосовали:\n"
        for user_id in non_voted:
            # We don't have user names for those who haven't voted yet
            status_message += f"• User ID: {user_id}\n"

    await update.message.reply_text(status_message)

async def stats_command(update, context):
    """Display poll statistics."""
    chat_id = str(update.effective_chat.id)
    
    # Обновляем название чата
    await update_chat_name(update, chat_id)
    
    stats = await db.get_poll_stats(chat_id, POLL_OPTIONS)
    
    total_polls = stats['total_polls']
    most_popular_result = stats['most_popular']
    times = stats['times']
    
    most_popular_option = "Нет данных"
    if most_popular_result:
        option_index, count = most_popular_result
        most_popular_option = f"{POLL_OPTIONS[option_index]} ({count} голосов)"
    
    avg_time = "Нет данных"
    if times:
        # Convert times to minutes since midnight
        minutes_list = []
        for (time_str,) in times:
            hour, minute = map(int, time_str.split(':'))
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
    
    try:
        # Базовый текст сообщения без ссылки
        stats_message = "📊 Статистика опросов\n\n"
        stats_message += f"Всего опросов: {total_polls}\n"
        stats_message += f"Самый популярный ответ: {most_popular_option}\n"
        stats_message += f"Среднее время запуска опроса: {avg_time}\n\n"
        
        # Определяем, локальный ли это адрес
        is_localhost = 'localhost' in stats_url or '127.0.0.1' in stats_url
        
        if is_localhost:
            # Для локальных URL используем обычный текст
            stats_message += "Подробная статистика доступна по ссылке:\n"
            stats_message += f"{stats_url}\n\n"
            stats_message += "⚠️ Локальная разработка: ссылка работает только на компьютере разработчика"
            
            # Отправляем сообщение без кнопки
            await update.message.reply_text(stats_message)
        else:
            # Для рабочих URL используем inline кнопку
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            
            stats_message += "Нажмите кнопку ниже для просмотра подробной статистики:"
            
            # Создаем inline кнопку с ссылкой
            keyboard = [[InlineKeyboardButton("Открыть детальную статистику", url=stats_url)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Отправляем сообщение с кнопкой
            await update.message.reply_text(stats_message, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Ошибка при отправке статистики: {e}")
        # Запасной вариант без форматирования
        fallback_message = f"📊 Статистика опросов\n\n"
        fallback_message += f"Всего опросов: {total_polls}\n"
        fallback_message += f"Самый популярный ответ: {most_popular_option}\n"
        fallback_message += f"Среднее время запуска опроса: {avg_time}\n\n"
        fallback_message += f"Подробная статистика доступна по ссылке:\n{stats_url}"
        await update.message.reply_text(fallback_message)

async def set_poll_time_command(update, context):
    """Set custom poll time for a chat."""
    chat_id = str(update.effective_chat.id)
    
    # Обновляем название чата
    await update_chat_name(update, chat_id)
    
    args = context.args
    
    if not args or len(args) < 1:
        await update.message.reply_text(
            "Пожалуйста, укажите время для опроса.\n"
            "Формат: /set_poll_time ЧЧ:ММ или ЧЧ:ММ AM/PM\n"
            "Примеры: /set_poll_time 21:30 или /set_poll_time 9:30 pm\n"
            "Время указывается в часовом поясе GMT+6."
        )
        return
    
    # Join all args in case there are spaces
    time_str = " ".join(args)
    
    # Parse and convert the time string to UTC
    utc_time_str = await scheduler.parse_time_string(time_str)
    
    if not utc_time_str:
        await update.message.reply_text(
            "Неверный формат времени. Используйте формат ЧЧ:ММ или ЧЧ:ММ AM/PM.\n"
            "Примеры: 21:30 или 9:30 pm"
        )
        return
    
    # Save to database
    success = await db.set_poll_time(chat_id, utc_time_str)
    
    if success:
        # Convert UTC back to GMT+6 for display
        hour, minute = map(int, utc_time_str.split(':'))
        dt = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
        dt += timedelta(hours=6)  # UTC to GMT+6
        gmt6_time = f"{dt.hour:02d}:{dt.minute:02d}"
        
        await update.message.reply_text(f"Время опроса установлено на {gmt6_time} (GMT+6).")
        
        # Reschedule the poll
        success = await scheduler.reschedule_poll_for_chat(
            context.job_queue,
            chat_id,
            send_poll
        )
        
        if not success:
            await update.message.reply_text(
                "Время сохранено, но возникла ошибка при планировании опроса. "
                "Перезапустите бота, чтобы применить изменения."
            )
    else:
        await update.message.reply_text("Произошла ошибка при сохранении времени опроса. Попробуйте позже.")

async def get_poll_time_command(update, context):
    """Display the currently configured poll time."""
    chat_id = str(update.effective_chat.id)

    # Обновляем название чата
    await update_chat_name(update, chat_id)

    poll_time_str = await db.get_poll_time(chat_id)

    # Convert UTC time back to GMT+6 for display
    hour, minute = map(int, poll_time_str.split(':'))
    dt = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
    dt += timedelta(hours=6)
    gmt6_time = f"{dt.hour:02d}:{dt.minute:02d}"

    await update.message.reply_text(f"Текущее время опроса: {gmt6_time} (GMT+6)")

async def link_steam_command(update, context):
    """Обработчик команды для привязки Steam ID через OAuth"""
    user = update.effective_user
    chat = update.effective_chat
    message = update.message
    chat_id = str(chat.id)
    
    # Обновляем название чата
    await update_chat_name(update, chat_id)
    
    if not await db.is_user_registered(user.id):
        await db.register_user(user)
    
    # Проверяем, есть ли уже привязанный Steam ID для этого чата
    is_linked = await db.is_steam_id_linked_to_chat(user.id, chat_id)
    
    if is_linked:
        # Получаем название чата
        chat_name = await db.get_chat_name_by_id(chat_id) or "этом чате"
        
        # Отправляем сообщение в личку пользователю
        try:
            # Формируем сообщение без кнопки авторизации
            await context.bot.send_message(
                chat_id=user.id,
                text=f"❌ Ваш Steam ID уже зарегистрирован в чате \"{chat_name}\", ничего делать не надо.\n\n"
                     f"Если вы хотите отвязать текущий аккаунт и привязать другой, сначала используйте команду /unlink_steam в нужном чате."
            )
            # Если это был групповой чат, отправляем уведомление туда
            if chat.type != 'private':
                await message.reply_text(
                    f"Я отправил тебе информацию в личные сообщения, @{user.username or user.first_name}"
                )
        except Exception as e:
            # Если не удалось отправить в личку, отправляем в чат
            logger.error(f"Error sending private message to {user.id}: {e}")
            await message.reply_text(
                f"❌ Ваш Steam ID уже зарегистрирован в чате \"{chat_name}\", ничего делать не надо.\n\n"
                f"Если вы хотите отвязать текущий аккаунт и привязать другой, сначала используйте команду /unlink_steam в нужном чате."
            )
        return
    
    # Получаем URL для авторизации через Steam OpenID с указанием ID чата
    auth_url = web_server.get_steam_auth_url(user.id, chat_id)
    
    # Создаем сообщение с инлайн-кнопкой для авторизации
    keyboard = [
        [InlineKeyboardButton("Войти через Steam", url=auth_url)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Отправляем сообщение с инструкциями либо в личку, либо в чат
    if chat.type == 'private':
        await message.reply_text(
            "Для привязки Steam аккаунта, нажмите кнопку ниже и войдите в свой аккаунт Steam. "
            "После авторизации ваш Steam ID будет автоматически привязан к вашему аккаунту Telegram.\n\n"
            "Это безопасный способ авторизации, использующий официальный Steam OpenID.",
            reply_markup=reply_markup
        )
    else:
        # Пробуем отправить в личные сообщения
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text="Для привязки Steam аккаунта, нажмите кнопку ниже и войдите в свой аккаунт Steam. "
                "После авторизации ваш Steam ID будет автоматически привязан к вашему аккаунту Telegram.\n\n"
                "Это безопасный способ авторизации, использующий официальный Steam OpenID.",
                reply_markup=reply_markup
            )
            # Отправляем уведомление в групповой чат
            await message.reply_text(
                f"Я отправил тебе инструкции по привязке Steam ID в личные сообщения, @{user.username or user.first_name}"
            )
        except Exception as e:
            # Если не удалось отправить в личку, отправляем в чат
            logger.error(f"Error sending private message to {user.id}: {e}")
            await message.reply_text(
                "Для привязки Steam аккаунта, нажмите кнопку ниже и войдите в свой аккаунт Steam. "
                "После авторизации ваш Steam ID будет автоматически привязан к вашему аккаунту Telegram.\n\n"
                "Это безопасный способ авторизации, использующий официальный Steam OpenID.",
                reply_markup=reply_markup
            )
    
    logger.info(f"User {user.id} ({user.username}) requested Steam authentication link for chat {chat_id}")

async def unlink_steam_command(update, context):
    """Отвязывает Steam ID от аккаунта пользователя."""
    user = update.effective_user
    user_id = user.id
    chat = update.effective_chat
    chat_id = str(chat.id)
    
    # Обновляем название чата
    await update_chat_name(update, chat_id)
    
    # Получаем информацию о пользователе
    user_info = await db.get_user_info(user_id)
    
    # Проверяем, привязан ли Steam ID к данному чату
    is_linked = await db.is_steam_id_linked_to_chat(user_id, chat_id)
    
    if not is_linked:
        if chat.type == 'private':
            await update.message.reply_text(
                "У вас нет привязанного Steam ID для этого чата. Чтобы привязать аккаунт, используйте команду /link_steam. ВНИМАНИЕ: команду нужно запускать внутри нужного чата, не здесь!!"
            )
        else:
            # Пробуем отправить в личные сообщения
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="У вас нет привязанного Steam ID для этого чата. Чтобы привязать аккаунт, используйте команду /link_steam. ВНИМАНИЕ: команду нужно запускать внутри нужного чата, не здесь!!"
                )
                await update.message.reply_text(
                    f"Я отправил тебе информацию в личные сообщения, @{user.username or user.first_name}"
                )
            except Exception as e:
                logger.error(f"Error sending private message to {user_id}: {e}")
                await update.message.reply_text(
                    "У вас нет привязанного Steam ID для этого чата. Чтобы привязать аккаунт, используйте команду /link_steam. ВНИМАНИЕ: команду нужно запускать внутри нужного чата, не здесь!!"
                )
        return
    
    if not user_info or not user_info['steam_id']:
        if chat.type == 'private':
            await update.message.reply_text(
                "У вас нет привязанного Steam ID. Чтобы привязать аккаунт, используйте команду /link_steam. ВНИМАНИЕ: команду нужно запускать внутри нужного чата, не здесь!!"
            )
        else:
            # Пробуем отправить в личные сообщения
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="У вас нет привязанного Steam ID. Чтобы привязать аккаунт, используйте команду /link_steam. ВНИМАНИЕ: команду нужно запускать внутри нужного чата, не здесь!!"
                )
                await update.message.reply_text(
                    f"Я отправил тебе информацию в личные сообщения, @{user.username or user.first_name}"
                )
            except Exception as e:
                logger.error(f"Error sending private message to {user_id}: {e}")
                await update.message.reply_text(
                    "У вас нет привязанного Steam ID. Чтобы привязать аккаунт, используйте команду /link_steam. ВНИМАНИЕ: команду нужно запускать внутри нужного чата, не здесь!!"
                )
        return
    
    # Получаем название чата
    chat_name = await db.get_chat_name_by_id(chat_id) or "этого чата"
    
    # Показываем информацию о текущем Steam аккаунте
    steam_id = user_info['steam_id']
    
    # Создаем кнопки для подтверждения отвязки
    keyboard = [
        [InlineKeyboardButton("Да, отвязать", callback_data=f"unlink_confirm:{user_id}:{chat_id}")],
        [InlineKeyboardButton("Отмена", callback_data=f"unlink_cancel:{user_id}:{chat_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Получаем API ключ Steam из переменных окружения
    steam_api_key = os.environ.get("STEAM_API_KEY")
    
    message_text = ""
    
    if steam_api_key:
        # Получаем информацию о профиле для отображения
        profile_data = await steam.verify_steam_id(steam_id, steam_api_key)
        
        if profile_data:
            steam_name = profile_data['username']
            profile_url = profile_data['profile_url']
            
            message_text = (
                f"🔄 <b>Отвязка Steam аккаунта</b>\n\n"
                f"Вы действительно хотите отвязать свой Steam аккаунт от чата \"{chat_name}\"?\n\n"
                f"<b>Текущий аккаунт:</b>\n"
                f"Steam ID: <code>{steam_id}</code>\n"
                f"Имя: {steam_name}\n\n"
                f"После отвязки бот не будет отслеживать ваш статус в Dota 2 для этого чата."
            )
            
            # Добавляем кнопку перехода в профиль
            keyboard.insert(0, [InlineKeyboardButton("Просмотреть профиль", url=profile_url)])
            reply_markup = InlineKeyboardMarkup(keyboard)
        else:
            message_text = (
                f"🔄 <b>Отвязка Steam аккаунта</b>\n\n"
                f"Вы действительно хотите отвязать свой Steam аккаунт (ID: <code>{steam_id}</code>) от чата \"{chat_name}\"?\n\n"
                f"После отвязки бот не будет отслеживать ваш статус в Dota 2 для этого чата."
            )
    else:
        message_text = (
            f"🔄 <b>Отвязка Steam аккаунта</b>\n\n"
            f"Вы действительно хотите отвязать свой Steam аккаунт (ID: <code>{steam_id}</code>) от чата \"{chat_name}\"?\n\n"
            f"После отвязки бот не будет отслеживать ваш статус в Dota 2 для этого чата."
        )
    
    # Отправляем сообщение с подтверждением в личку или в чат
    if chat.type == 'private':
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        # Пробуем отправить в личные сообщения
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=message_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            await update.message.reply_text(
                f"Я отправил тебе инструкции по отвязке Steam ID в личные сообщения, @{user.username or user.first_name}"
            )
        except Exception as e:
            logger.error(f"Error sending private message to {user_id}: {e}")
            await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='HTML')
    
    logger.info(f"User {user.first_name} ({user_id}) requested to unlink Steam ID {steam_id} from chat {chat_id}")

async def handle_unlink_steam_confirm(update, context):
    """Обрабатывает подтверждение отвязки Steam ID."""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    parts = callback_data.split(':')
    user_id = int(parts[1])
    chat_id = parts[2] if len(parts) > 2 else None
    current_user_id = query.from_user.id
    
    # Проверяем, что кнопку нажал именно тот пользователь, который запросил отвязку
    if user_id != current_user_id:
        await query.edit_message_text(
            "Ошибка: эта кнопка предназначена для другого пользователя."
        )
        return
    
    # Получаем название чата
    chat_name = await db.get_chat_name_by_id(chat_id) if chat_id else "неизвестного чата"
    
    # Отвязываем Steam ID
    success = await db.remove_user_steam_id(user_id, chat_id)
    
    if success:
        await query.edit_message_text(
            f"✅ Ваш Steam аккаунт успешно отвязан от чата \"{chat_name}\".\n\n"
            f"Теперь бот не будет отслеживать ваш статус в Dota 2 для этого чата.\n"
            f"Вы можете привязать другой аккаунт с помощью команды /link_steam.",
            parse_mode='HTML'
        )
        logger.info(f"User {query.from_user.first_name} ({user_id}) unlinked their Steam ID from chat {chat_id}")
    else:
        await query.edit_message_text(
            "❌ Произошла ошибка при отвязке Steam аккаунта. Пожалуйста, попробуйте позже."
        )
        logger.error(f"Error unlinking Steam ID for user {user_id} from chat {chat_id}")

async def handle_unlink_steam_cancel(update, context):
    """Обрабатывает отмену отвязки Steam ID."""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    parts = callback_data.split(':')
    user_id = parts[1]
    chat_id = parts[2] if len(parts) > 2 else None
    
    await query.edit_message_text(
        "❌ Отвязка Steam аккаунта отменена. Ваш аккаунт остается привязанным."
    )
    
    logger.info(f"User {query.from_user.first_name} ({user_id}) canceled unlinking Steam ID from chat {chat_id}")

async def handle_poll_answer(update, context):
    """Handle when a user answers the poll."""
    answer = update.poll_answer
    poll_id = answer.poll_id
    user = update.effective_user
    selected_option = answer.option_ids[0] if answer.option_ids else None

    # Record this vote
    if selected_option is not None:
        await poll_state.add_vote(poll_id, user, selected_option)

    # Проверяем, не является ли чат личным
    for chat_id, poll_data in list(poll_state.active_polls.items()):
        if poll_data["poll_id"] == poll_id:
            # Получаем числовой ID чата
            numeric_chat_id = int(chat_id) if chat_id.lstrip('-').isdigit() else chat_id
            
            # Личные чаты имеют положительный ID
            is_personal_chat = isinstance(numeric_chat_id, int) and numeric_chat_id > 0
            
            # Если это личный чат - не завершаем опрос сразу после единственного голоса
            if is_personal_chat:
                logger.info(f"Голос в личном чате {chat_id}, ожидаем таймаута")
                return
            
            # Для групповых чатов - завершаем опрос, если проголосовали все
            if poll_data["all_users"] and poll_data["all_users"].issubset(poll_data["voted_users"]):
                logger.info(f"Все пользователи проголосовали в чате {chat_id}, завершаем опрос")
                await process_poll_results(chat_id, context)
            break

async def send_poll(chat_id, context, message, manual=False):
    """Send a poll to the specified chat."""
    try:
        # Если chat_id это строка с числом, конвертируем в int для Telegram API
        numeric_chat_id = int(chat_id) if chat_id.lstrip('-').isdigit() else chat_id
        
        # Получаем информацию о чате для обновления названия
        try:
            chat = await context.bot.get_chat(numeric_chat_id)
            if chat.title:
                await db.set_chat_name(chat_id, chat.title)
                logger.info(f"Updated chat name from send_poll: {chat_id} -> {chat.title}")
        except Exception as e:
            logger.warning(f"Could not get chat info for {chat_id}: {e}")
        
        # Send the leading message
        await context.bot.send_message(chat_id=numeric_chat_id, text=message)

        # Send the actual poll
        poll_message = await context.bot.send_poll(
            chat_id=numeric_chat_id,
            question=POLL_QUESTION,
            options=POLL_OPTIONS,
            is_anonymous=False,
        )

        # Store poll information
        poll_id = poll_message.poll.id
        message_id = poll_message.message_id
        trigger_type = "manual" if manual else "scheduled"
        await poll_state.create_poll(chat_id, poll_id, message_id, trigger_type)

        # Get chat members to track who needs to vote
        try:
            chat_members = await context.bot.get_chat_administrators(numeric_chat_id)
            for member in chat_members:
                if not member.user.is_bot:
                    poll_state.add_user_to_chat(chat_id, member.user.id)
        except BadRequest:
            # This might fail in some chat types
            logger.warning(f"Couldn't get chat members for {chat_id}")

        # Schedule the first reminder (after 10 minutes)
        first_reminder = context.application.create_task(
            send_reminder(chat_id, context, 10 * 60)
        )

        # Schedule poll closing (after 20 minutes)
        poll_timeout = context.application.create_task(
            close_poll_after_timeout(chat_id, context, 20 * 60)
        )

        # Save the final task (it will cancel and replace any previous tasks)
        poll_state.set_task(chat_id, poll_timeout)
    except Exception as e:
        logger.error(f"Error in send_poll: {e}", exc_info=True)

async def send_reminder(chat_id, context, delay):
    """Send a reminder to users who haven't voted."""
    await asyncio.sleep(delay)

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
        # Получаем информацию о пользователе из базы данных
        user_info = await db.get_user_info(user_id)
        if user_info and user_info['username']:
            # Если у пользователя есть username, используем его для упоминания
            ping_message += f"@{user_info['username']} "
        elif user_info and user_info['first_name']:
            # Если нет username, то используем имя
            ping_message += f"{user_info['first_name']} "
        else:
            # Если нет информации о пользователе, используем ID
            ping_message += f"ID:{user_id} "

    if ping_message:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Напоминание о голосовании: {ping_message}"
        )

async def close_poll_after_timeout(chat_id, context, delay):
    """Close the poll after the specified delay."""
    await asyncio.sleep(delay)

    # Check if poll is still active
    if not poll_state.is_active(chat_id):
        return

    poll_data = poll_state.get_poll_data(chat_id)

    try:
        # Stop the poll in Telegram
        await context.bot.stop_poll(
            chat_id=chat_id,
            message_id=poll_data["message_id"]
        )
    except BadRequest:
        # Poll might already be closed
        pass

    # Process the results
    await process_poll_results(chat_id, context)

async def process_poll_results(chat_id, context):
    """Process the poll results and send the appropriate message."""
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
        for category, indices in CATEGORY_MAPPING.items():
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
    if categories["accepted"] and not categories["declined"] and not categories["deferred"]:
        result_message = "Сасают все!"
    elif categories["declined"] and not categories["accepted"] and not categories["deferred"]:
        result_message = "Сегодня никто не хочет сасать, даешь отдых глотке!"
    elif not categories["accepted"] and not categories["declined"] and not categories["deferred"]:
        result_message = "Сегодня никто не хочет сасать, даешь отдых глотке!"
    elif not categories["accepted"] and not categories["declined"] and categories["deferred"]:
        result_message = f"Пока что никто не готов сасать, предлагали подождать {deferred_delay} минут"
    else:
        result_message = ""
        if categories["accepted"]:
            result_message += f"Готовы сасать: {', '.join(categories['accepted'])}! "
        if categories["declined"]:
            result_message += f"Отказались сасать: {', '.join(categories['declined'])}. "
        if categories["deferred"]:
            result_message += f"Откладывают сасание: {', '.join(categories['deferred'])}. "

    # Add info about users who didn't vote
    non_voted = poll_data["all_users"] - poll_data["voted_users"]
    if non_voted and poll_data["first_ping_sent"]:
        # Получаем имена пользователей, которые не проголосовали
        non_voted_names = []
        for user_id in non_voted:
            user_info = await db.get_user_info(user_id)
            if user_info:
                if user_info['username']:
                    non_voted_names.append(f"@{user_info['username']}")
                elif user_info['first_name']:
                    non_voted_names.append(user_info['first_name'])
                else:
                    non_voted_names.append(f"ID:{user_id}")
            else:
                non_voted_names.append(f"ID:{user_id}")
        
        result_message += f"\nНе проголосовали: {', '.join(non_voted_names)}"

    # Send result message
    await context.bot.send_message(chat_id=chat_id, text=result_message)

    # Close the poll in our state
    await poll_state.close_poll(chat_id)

async def schedule_new_poll(chat_id, context, delay):
    """Schedule a new poll after the specified delay."""
    await asyncio.sleep(delay)
    await send_poll(chat_id, context, "Ah shit, here we go again!")

async def setup_commands(application):
    """Set up bot commands to be suggested in the Telegram UI."""
    commands = [
        BotCommand("pol_now", "Начать опрос вручную"),
        BotCommand("status", "Проверить статус текущего опроса"),
        BotCommand("stop_poll", "Остановить текущий опрос"),
        BotCommand("link_steam", "Привязать Steam ID"),
        BotCommand("unlink_steam", "Отвязать Steam ID"),
        BotCommand("who_is_playing", "Показать кто играет в Dota 2"),
        BotCommand("stats", "Статистика опросов"),
        BotCommand("set_poll_time", "Установить время опроса (ЧЧ:ММ)"),
        BotCommand("get_poll_time", "Показать установленное время опроса")
    ]
    
    # Set commands globally
    await application.bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    
    # Set commands for all registered chats
    for chat_id in poll_state.registered_chats:
        try:
            await application.bot.set_my_commands(
                commands, 
                scope=BotCommandScopeChat(chat_id=chat_id)
            )
            logger.info(f"Commands set up for chat {chat_id}")
        except Exception as e:
            logger.error(f"Failed to set commands for chat {chat_id}: {e}")
    
    logger.info("Bot commands have been set up")

async def who_is_playing_command(update, context):
    """Отображает статус Steam пользователей в текущем чате"""
    chat_id = str(update.effective_chat.id)
    
    # Обновляем название чата
    await update_chat_name(update, chat_id)
    
    try:
        # Отправляем сообщение о начале проверки
        status_message = await update.message.reply_text("🔍 Проверяю статус игроков...", reply_to_message_id=update.message.message_id)
        
        # Получаем Steam API ключ
        steam_api_key = os.environ.get("STEAM_API_KEY")
        if not steam_api_key:
            await status_message.edit_text("⚠️ Не задан API ключ Steam. Обратитесь к администратору бота.")
            return
        
        # Получаем пользователей из базы данных вместо API Telegram
        user_steam_ids = {}
        
        try:
            # Используем SQLite для получения пользователей привязанных к текущему чату
            async with db.db_semaphore:
                with db.safe_db_connect() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                    SELECT usc.telegram_id, usc.steam_id, u.first_name
                    FROM user_steam_chats usc
                    JOIN users u ON usc.telegram_id = u.telegram_id
                    WHERE usc.chat_id = ? AND usc.steam_id IS NOT NULL
                    """, (chat_id,))
                    
                    steam_users = cursor.fetchall()
                    
            logger.info(f"Найдено {len(steam_users)} пользователей с привязанными Steam ID в чате {chat_id}")
            
            # Списки для хранения пользователей по категориям
            dota_players = []
            online_users = []
            offline_users = []
            other_game_players = []
            
            # Если в чате нет привязанных пользователей
            if not steam_users:
                await status_message.edit_text("⚠️ В этом чате нет пользователей с привязанными Steam ID.\n\nИспользуйте команду /link_steam для привязки аккаунта.")
                return
                
            # Заполняем словарь пользователей для проверки
            for user_id, steam_id, first_name in steam_users:
                user_steam_ids[user_id] = {
                    'steam_id': steam_id,
                    'first_name': first_name,
                    'has_link_issue': False
                }
                
            # Проверка статуса Steam для пользователей с привязанным Steam ID
            if user_steam_ids:
                # Создаем SSL-контекст для запросов
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                
                # Добавляем промежуточное сообщение, чтобы пользователь знал, что происходит
                if len(user_steam_ids) > 1:
                    await status_message.edit_text(f"🔍 Проверяю статус {len(user_steam_ids)} игроков...\n\nЭто может занять некоторое время из-за ограничений Steam API.")
                
                # Проверяем статус каждого пользователя с интервалом в 2 секунды
                for i, (user_id, user_data) in enumerate(user_steam_ids.items()):
                    steam_id = user_data['steam_id']
                    first_name = user_data['first_name']
                    
                    # Добавляем задержку между запросами, чтобы избежать ограничения Steam API
                    if i > 0:
                        await asyncio.sleep(2)  # Ждем 2 секунды между запросами
                    
                    # Обновляем сообщение, чтобы пользователь видел прогресс
                    if len(user_steam_ids) > 1:
                        await status_message.edit_text(f"🔍 Проверяю статус {i+1}/{len(user_steam_ids)} игроков...\n\nСейчас проверяю: {first_name}")
                    
                    try:
                        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
                            url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={steam_api_key}&steamids={steam_id}"
                            
                            # Добавляем повторные попытки запроса в случае ошибки 429
                            max_retries = 3
                            for retry in range(max_retries):
                                try:
                                    async with session.get(url) as response:
                                        if response.status == 429:  # Too Many Requests
                                            logger.warning(f"Ошибка API Steam 429 для пользователя {first_name}, попытка {retry+1}/{max_retries}")
                                            if retry < max_retries - 1:
                                                wait_time = (retry + 1) * 5  # Увеличиваем время ожидания с каждой попыткой
                                                await asyncio.sleep(wait_time)
                                                continue  # Повторяем запрос
                                            else:
                                                logger.error(f"Исчерпаны попытки запроса к Steam API для пользователя {first_name}")
                                                offline_users.append(first_name)
                                                break
                                        
                                        if response.status != 200:
                                            logger.error(f"Ошибка API Steam: {response.status} для пользователя {first_name}")
                                            offline_users.append(first_name)
                                            break
                                        
                                        data = await response.json()
                                        players = data.get('response', {}).get('players', [])
                                        
                                        if not players:
                                            logger.warning(f"Нет данных о пользователе Steam {steam_id}")
                                            offline_users.append(first_name)
                                            break
                                        
                                        player = players[0]
                                        
                                        # Определяем статус игрока
                                        persona_state = player.get('personastate', 0)  # 0 = offline, 1+ = online
                                        game_id = player.get('gameid', None)
                                        game_name = player.get('gameextrainfo', None)
                                        
                                        # Логируем полную информацию о пользователе
                                        logger.info(f"Статус Steam для {first_name}: персона={persona_state}, игра={game_id} ({game_name})")
                                        
                                        if game_id == "570":  # Dota 2
                                            dota_players.append(first_name)
                                            logger.info(f"Пользователь {first_name} играет в Dota 2")
                                        elif game_id:  # Другая игра
                                            game_display_name = game_name or "Неизвестная игра"
                                            other_game_players.append((first_name, game_display_name))
                                            logger.info(f"Пользователь {first_name} играет в {game_display_name}")
                                        elif persona_state > 0:  # Онлайн, но не в игре
                                            online_users.append(first_name)
                                            logger.info(f"Пользователь {first_name} онлайн")
                                        else:  # Оффлайн
                                            offline_users.append(first_name)
                                            logger.info(f"Пользователь {first_name} оффлайн")
                                        
                                        # Успешно получили данные, выходим из цикла повторов
                                        break
                                except Exception as e:
                                    logger.error(f"Ошибка при запросе к Steam API для {first_name}: {e}")
                                    if retry < max_retries - 1:
                                        wait_time = (retry + 1) * 5
                                        await asyncio.sleep(wait_time)
                                    else:
                                        offline_users.append(first_name)
                                        break
                                    
                    except Exception as e:
                        logger.error(f"Ошибка при получении данных Steam для {first_name} ({steam_id}): {e}")
                        offline_users.append(first_name)
            
            # Формируем короткое сообщение о статусе
            if len(offline_users) == len(user_steam_ids) and user_steam_ids:
                status_text = "Сейчас все оффлайн"
            elif len(dota_players) == len(user_steam_ids) and user_steam_ids:
                status_text = "Сейчас все играют в Dota 2"
            else:
                lines = []

                if dota_players:
                    lines.append("В Dota 2:")
                    lines.append(", ".join(dota_players))

                if other_game_players:
                    lines.append("В другой игре:")

                    game_groups = {}
                    for name, game in other_game_players:
                        game_groups.setdefault(game, []).append(name)

                    for game, players in game_groups.items():
                        players_str = ", ".join(players)
                        lines.append(f"{players_str}: {game}")

                if online_users:
                    lines.append("Онлайн:")
                    lines.append(", ".join(online_users))

                if offline_users and len(offline_users) != len(user_steam_ids):
                    lines.append("Оффлайн:")
                    lines.append(", ".join(offline_users))

                lines.append(f"Проверено пользователей: {len(user_steam_ids)}")

                if lines:
                    status_text = "\n".join(lines)
                else:
                    status_text = "Сейчас никто не играет"

            # Отправляем сообщение
            await status_message.edit_text(status_text)
        
        except Exception as e:
            logger.error(f"Ошибка при получении пользователей из базы данных: {e}")
            await status_message.edit_text(f"❌ Ошибка при получении данных из базы: {str(e)}")
            return
    
    except Exception as e:
        logger.error(f"Ошибка в команде who_is_playing: {e}")
        await update.message.reply_text(f"❌ Произошла ошибка: {str(e)}") 
