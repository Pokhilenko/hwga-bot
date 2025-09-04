# Poll settings
POLL_QUESTION = "Сасать?"
POLL_OPTIONS = [
    "Конечно, нахуй, да!",
    "Со вчерашнего рот болит",
    "5-10 минут и готов сасать",
    "Полчасика и буду пасасэо",
    "Часик и го"
]

# Category mapping for poll results
CATEGORY_MAPPING = {
    "accepted": [0],
    "declined": [1],
    "deferred": [2, 3, 4],
}

# Messages
MSG_WELCOME = (
    "Привет! Я бот для опросов.\n"
    "/poll_now - начать опрос вручную\n"
    "/status - проверить статус текущего опроса\n"
    "/stop_poll - остановить текущий опрос\n"
    "/link_steam - привязать Steam ID\n"
    "/unlink_steam - отвязать Steam ID\n"
    "/stats - статистика опросов\n"
    "/set_poll_time - установить время опроса (ЧЧ:ММ)\n"
    "/get_poll_time - показать установленное время опроса"
)
MSG_POLL_ALREADY_ACTIVE = "Опрос уже активен."
MSG_NO_ACTIVE_POLL = "Нет активного отсоса."
MSG_MANUAL_POLL_INVITATION = "{user_name} приглашает всех на посасать!"
MSG_POLL_STATUS = "Статус опроса:"
MSG_VOTED = "Проголосовали:"
MSG_NOT_VOTED_YET = "Еще не проголосовали:"
MSG_STATS_TITLE = "📊 Статистика опросов"
MSG_TOTAL_POLLS = "Всего опросов: {total_polls}"
MSG_MOST_POPULAR_OPTION = "Самый популярный ответ: {option} ({count} голосов)"
MSG_AVG_POLL_TIME = "Среднее время запуска опроса: {time} (GMT+6)"
MSG_STATS_URL = "Подробная статистика доступна по ссылке: {url}"
MSG_STATS_URL_BUTTON = "Нажмите кнопку ниже для просмотра подробной статистики:"
MSG_STATS_URL_LOCAL_WARNING = "⚠️ Локальная разработка: ссылка работает только на компьютере разработчика"
MSG_SET_POLL_TIME_PROMPT = (
    "Пожалуйста, укажите время для опроса.\n"
    "Формат: /set_poll_time ЧЧ:ММ или ЧЧ:ММ AM/PM\n"
    "Примеры: /set_poll_time 21:30 или /set_poll_time 9:30 pm\n"
    "Время указывается в часовом поясе GMT+6."
)
MSG_INVALID_TIME_FORMAT = (
    "Неверный формат времени. Используйте формат ЧЧ:ММ или ЧЧ:ММ AM/PM.\n"
    "Примеры: 21:30 или 9:30 pm"
)
MSG_POLL_TIME_SET = "Время опроса установлено на {time} (GMT+6)."
MSG_POLL_TIME_SAVE_ERROR = "Произошла ошибка при сохранении времени опроса. Попробуйте позже."
MSG_POLL_RESCHEDULE_ERROR = (
    "Время сохранено, но возникла ошибка при планировании опроса. "
    "Перезапустите бота, чтобы применить изменения."
)
MSG_CURRENT_POLL_TIME = "Текущее время опроса: {time} (GMT+6)"
MSG_STEAM_ID_ALREADY_LINKED = '❌ Ваш Steam ID уже зарегистрирован в чате "{chat_name}", ничего делать не надо.\n\nЕсли вы хотите отвязать текущий аккаунт и привязать другой, сначала используйте команду /unlink_steam в нужном чате.'
MSG_STEAM_LINK_PROMPT = "Для привязки Steam аккаунта, нажмите кнопку ниже и войдите в свой аккаунт Steam. После авторизации ваш Steam ID будет автоматически привязан к вашему аккаунту Telegram.\n\nЭто безопасный способ авторизации, использующий официальный Steam OpenID."
MSG_STEAM_ID_NOT_LINKED = "У вас нет привязанного Steam ID для этого чата. Чтобы привязать аккаунт, используйте команду /link_steam. ВНИМАНИЕ: команду нужно запускать внутри нужного чата, не здесь!!"
MSG_UNLINK_STEAM_CONFIRM = (
    f"🔄 <b>Отвязка Steam аккаунта</b>\n\n"
    f'Вы действительно хотите отвязать свой Steam аккаунт от чата "{{chat_name}}"?\n\n' 
    f"<b>Текущий аккаунт:</b>\n"
    f"Steam ID: <code>{{steam_id}}</code>\n"
    f"Имя: {{steam_name}}\n\n"
    f"После отвязки бот не будет отслеживать ваш статус в Dota 2 для этого чата."
)
MSG_UNLINK_STEAM_CONFIRM_NO_PROFILE = (
    f"🔄 <b>Отвязка Steam аккаунта</b>\n\n"
    f'Вы действительно хотите отвязать свой Steam аккаунт (ID: <code>{{steam_id}}</code>) от чата "{{chat_name}}"?\n\n' 
    f"После отвязки бот не будет отслеживать ваш статус в Dota 2 для этого чата."
)
MSG_UNLINK_STEAM_SUCCESS = '✅ Ваш Steam аккаунт успешно отвязан от чата "{chat_name}".\n\nТеперь бот не будет отслеживать ваш статус в Dota 2 для этого чата.\nВы можете привязать другой аккаунт с помощью команды /link_steam.'
MSG_UNLINK_STEAM_ERROR = "❌ Произошла ошибка при отвязке Steam аккаунта. Пожалуйста, попробуйте позже."
MSG_UNLINK_STEAM_CANCEL = "❌ Отвязка Steam аккаунта отменена. Ваш аккаунт остается привязанным."
MSG_WHO_IS_PLAYING_CHECKING = "🔍 Проверяю статус игроков..."
MSG_STEAM_API_KEY_MISSING = "⚠️ Не задан API ключ Steam. Обратитесь к администратору бота."
MSG_WHO_IS_PLAYING_ERROR = "❌ Произошла ошибка: {error}"
MSG_POLL_RESULT_ALL_ACCEPTED = "Сасают все!"
MSG_POLL_RESULT_ALL_DECLINED = "Сегодня никто не хочет сасать, даешь отдых глотке!"
MSG_POLL_RESULT_ALL_DEFERRED = "Пока что никто не готов сасать, предлагали подождать {delay} минут"
MSG_POLL_RESULT_ACCEPTED = "Готовы сасать: {users}! "
MSG_POLL_RESULT_DECLINED = "Отказались сасать: {users}. "
MSG_POLL_RESULT_DEFERRED = "Откладывают сасание: {users}. "
MSG_POLL_RESULT_NOT_VOTED = "\nНе проголосовали: {users}"
MSG_REMINDER = "Напоминание о голосовании: {users}"
MSG_NEW_POLL = "Ah shit, here we go again!"