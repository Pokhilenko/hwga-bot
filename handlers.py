import asyncio
import logging
import random
import string
from datetime import datetime, timedelta
import re
import os

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

# Состояния для верификации Steam аккаунта
STEAM_VERIFICATION_WAITING = 1
STEAM_VERIFICATION_COMPLETE = 2

# Словарь для хранения информации о верификации пользователей
# {user_id: {'steam_id': '123', 'verification_code': 'ABC123', 'profile_url': 'url'}}
verification_data = {}

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
        "/register_me - зарегистрироваться\n"
        "/set_poll_time - установить время опроса (ЧЧ:ММ)"
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

async def register_me_command(update, context):
    """Register a user in the database."""
    chat_id = str(update.effective_chat.id)
    user = update.effective_user
    
    # Обновляем название чата
    await update_chat_name(update, chat_id)
    
    # Check if user is already registered
    is_registered = await db.is_user_registered(user.id)
    
    if is_registered:
        await update.message.reply_text("Вы уже зарегистрированы.")
        return
    
    # Register the user
    success = await db.register_user(user)
    
    if success:
        await update.message.reply_text(f"Вы успешно зарегистрированы, {user.first_name}!")
    else:
        await update.message.reply_text("Произошла ошибка при регистрации. Попробуйте позже.")

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

async def link_steam_command(update, context):
    """Обработчик команды для привязки Steam ID"""
    user = update.effective_user
    chat = update.effective_chat
    message = update.message
    
    if not await db.is_user_registered(user.id):
        await db.register_user(user)
    
    # Получаем URL для авторизации через Steam OpenID
    auth_url = web_server.get_steam_auth_url(user.id)
    
    # Создаем сообщение с инлайн-кнопкой для авторизации
    keyboard = [
        [InlineKeyboardButton("Войти через Steam", url=auth_url)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_text(
        "Для привязки Steam аккаунта, нажмите кнопку ниже и войдите в свой аккаунт Steam. "
        "После авторизации ваш Steam ID будет автоматически привязан к вашему аккаунту Telegram.\n\n"
        "Это безопасный способ авторизации, использующий официальный Steam OpenID.",
        reply_markup=reply_markup
    )
    
    logger.info(f"User {user.id} ({user.username}) requested Steam authentication link")

async def check_steam_verification(update, context):
    """Проверяет код верификации в профиле Steam."""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    user_id = callback_data.split(':')[1]
    current_user_id = str(query.from_user.id)
    
    # Проверяем, что кнопку нажал именно тот пользователь, который начал верификацию
    if user_id != current_user_id:
        await query.edit_message_text(
            "Ошибка: эта кнопка предназначена для другого пользователя."
        )
        return ConversationHandler.END
    
    # Проверяем наличие данных верификации
    if user_id not in verification_data:
        await query.edit_message_text(
            "Ошибка: данные верификации не найдены или устарели. Пожалуйста, начните процесс заново с команды /link_steam."
        )
        return ConversationHandler.END
    
    # Получаем данные верификации
    verification = verification_data[user_id]
    steam_id = verification['steam_id']
    verification_code = verification['verification_code']
    original_username = verification['username']
    
    # Получаем API ключ Steam
    steam_api_key = os.environ.get("STEAM_API_KEY")
    
    # Проверяем наличие кода в имени пользователя
    is_verified = await steam.check_verification_code(steam_id, verification_code, steam_api_key)
    
    if is_verified:
        # Верификация успешна, сохраняем Steam ID в базе данных
        success = await db.update_user_steam_id(int(user_id), steam_id)
        
        if success:
            # Получаем обновленную информацию о профиле
            profile_data = await steam.verify_steam_id(steam_id, steam_api_key)
            
            if profile_data:
                steam_name = profile_data['username']
                profile_url = profile_data['profile_url']
                visibility = "публичный" if profile_data['visibility'] == 3 else "приватный"
                status = "онлайн" if profile_data['status'] == 1 else "оффлайн"
                
                message_text = (
                    f"✅ <b>Верификация успешно завершена!</b>\n\n"
                    f"Steam ID <code>{steam_id}</code> успешно привязан к вашему аккаунту.\n\n"
                    f"<b>Информация о профиле:</b>\n"
                    f"Имя в Steam: {steam_name}\n"
                    f"Статус: {status}\n"
                    f"Видимость профиля: {visibility}\n\n"
                    f"Теперь вы можете вернуть исходное имя в Steam профиле.\n"
                    f"Бот будет отслеживать ваш статус игры в Dota 2."
                )
                
                # Обновляем сообщение с результатом верификации
                keyboard = [[InlineKeyboardButton("Открыть Steam профиль", url=profile_url)]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='HTML')
                logger.info(f"User {query.from_user.first_name} ({user_id}) successfully verified Steam ID {steam_id}")
            else:
                await query.edit_message_text(
                    "✅ Steam ID успешно верифицирован и привязан к вашему аккаунту, "
                    "но произошла ошибка при получении информации о профиле."
                )
        else:
            await query.edit_message_text(
                "Верификация прошла успешно, но произошла ошибка при сохранении Steam ID. "
                "Пожалуйста, попробуйте позже."
            )
        
        # Удаляем данные верификации
        if user_id in verification_data:
            del verification_data[user_id]
        
        return STEAM_VERIFICATION_COMPLETE
    else:
        # Верификация не удалась, предлагаем попробовать снова
        message_text = (
            f"❌ <b>Верификация не удалась</b>\n\n"
            f"Код <code>{verification_code}</code> не найден в имени вашего Steam профиля.\n\n"
            f"Убедитесь, что:\n"
            f"- Вы добавили код <code>{verification_code}</code> в имя профиля\n"
            f"- Вы сохранили изменения\n"
            f"- Прошло достаточно времени для обновления данных (до 1 минуты)\n\n"
            f"Исходное имя профиля: <b>{original_username}</b>"
        )
        
        # Обновляем сообщение с ошибкой верификации
        keyboard = [
            [InlineKeyboardButton("Открыть Steam профиль", url=verification['profile_url'])],
            [InlineKeyboardButton("Проверить снова", callback_data=f"verify_steam:{user_id}")],
            [InlineKeyboardButton("Отмена", callback_data=f"cancel_steam:{user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='HTML')
        logger.info(f"Verification failed for user {query.from_user.first_name} ({user_id}): code not found in Steam name")
        
        return STEAM_VERIFICATION_WAITING

async def cancel_steam_verification(update, context):
    """Отменяет процесс верификации Steam ID."""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    user_id = callback_data.split(':')[1]
    
    # Удаляем данные верификации
    if user_id in verification_data:
        del verification_data[user_id]
    
    await query.edit_message_text(
        "❌ Верификация Steam ID отменена. Вы можете начать процесс заново с помощью команды /link_steam."
    )
    
    logger.info(f"User {query.from_user.first_name} ({user_id}) canceled Steam verification")
    return ConversationHandler.END

async def unlink_steam_command(update, context):
    """Отвязывает Steam ID от аккаунта пользователя."""
    user = update.effective_user
    user_id = user.id
    chat_id = str(update.effective_chat.id)
    
    # Обновляем название чата
    await update_chat_name(update, chat_id)
    
    # Получаем информацию о пользователе
    user_info = await db.get_user_info(user_id)
    
    if not user_info or not user_info['steam_id']:
        await update.message.reply_text(
            "У вас нет привязанного Steam ID. Чтобы привязать аккаунт, используйте команду /link_steam."
        )
        return
    
    # Показываем информацию о текущем Steam аккаунте
    steam_id = user_info['steam_id']
    
    # Создаем кнопки для подтверждения отвязки
    keyboard = [
        [InlineKeyboardButton("Да, отвязать", callback_data=f"unlink_confirm:{user_id}")],
        [InlineKeyboardButton("Отмена", callback_data=f"unlink_cancel:{user_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Получаем API ключ Steam из переменных окружения
    steam_api_key = os.environ.get("STEAM_API_KEY")
    
    if steam_api_key:
        # Получаем информацию о профиле для отображения
        profile_data = await steam.verify_steam_id(steam_id, steam_api_key)
        
        if profile_data:
            steam_name = profile_data['username']
            profile_url = profile_data['profile_url']
            
            message_text = (
                f"🔄 <b>Отвязка Steam аккаунта</b>\n\n"
                f"Вы действительно хотите отвязать свой Steam аккаунт?\n\n"
                f"<b>Текущий аккаунт:</b>\n"
                f"Steam ID: <code>{steam_id}</code>\n"
                f"Имя: {steam_name}\n\n"
                f"После отвязки бот не будет отслеживать ваш статус в Dota 2."
            )
            
            # Добавляем кнопку перехода в профиль
            keyboard.insert(0, [InlineKeyboardButton("Просмотреть профиль", url=profile_url)])
            reply_markup = InlineKeyboardMarkup(keyboard)
        else:
            message_text = (
                f"🔄 <b>Отвязка Steam аккаунта</b>\n\n"
                f"Вы действительно хотите отвязать свой Steam аккаунт (ID: <code>{steam_id}</code>)?\n\n"
                f"После отвязки бот не будет отслеживать ваш статус в Dota 2."
            )
    else:
        message_text = (
            f"🔄 <b>Отвязка Steam аккаунта</b>\n\n"
            f"Вы действительно хотите отвязать свой Steam аккаунт (ID: <code>{steam_id}</code>)?\n\n"
            f"После отвязки бот не будет отслеживать ваш статус в Dota 2."
        )
    
    await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='HTML')
    logger.info(f"User {user.first_name} ({user_id}) requested to unlink Steam ID {steam_id}")

async def handle_unlink_steam_confirm(update, context):
    """Обрабатывает подтверждение отвязки Steam ID."""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    user_id = int(callback_data.split(':')[1])
    current_user_id = query.from_user.id
    
    # Проверяем, что кнопку нажал именно тот пользователь, который запросил отвязку
    if user_id != current_user_id:
        await query.edit_message_text(
            "Ошибка: эта кнопка предназначена для другого пользователя."
        )
        return
    
    # Отвязываем Steam ID
    success = await db.remove_user_steam_id(user_id)
    
    if success:
        await query.edit_message_text(
            "✅ Ваш Steam аккаунт успешно отвязан.\n\n"
            "Теперь бот не будет отслеживать ваш статус в Dota 2.\n"
            "Вы можете привязать другой аккаунт с помощью команды /link_steam.",
            parse_mode='HTML'
        )
        logger.info(f"User {query.from_user.first_name} ({user_id}) unlinked their Steam ID")
    else:
        await query.edit_message_text(
            "❌ Произошла ошибка при отвязке Steam аккаунта. Пожалуйста, попробуйте позже."
        )
        logger.error(f"Error unlinking Steam ID for user {user_id}")

async def handle_unlink_steam_cancel(update, context):
    """Обрабатывает отмену отвязки Steam ID."""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    user_id = callback_data.split(':')[1]
    
    await query.edit_message_text(
        "❌ Отвязка Steam аккаунта отменена. Ваш аккаунт остается привязанным."
    )
    
    logger.info(f"User {query.from_user.first_name} ({user_id}) canceled unlinking Steam ID")

async def handle_poll_answer(update, context):
    """Handle when a user answers the poll."""
    answer = update.poll_answer
    poll_id = answer.poll_id
    user = update.effective_user
    selected_option = answer.option_ids[0] if answer.option_ids else None

    # Record this vote
    if selected_option is not None:
        await poll_state.add_vote(poll_id, user, selected_option)

    # Check if all users have voted
    for chat_id, poll_data in poll_state.active_polls.items():
        if poll_data["poll_id"] == poll_id:
            if poll_data["all_users"] and poll_data["all_users"].issubset(poll_data["voted_users"]):
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
        BotCommand("stats", "Статистика опросов"),
        BotCommand("register_me", "Зарегистрироваться"),
        BotCommand("set_poll_time", "Установить время опроса (ЧЧ:ММ)")
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