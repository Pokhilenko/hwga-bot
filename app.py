import logging
import os
import datetime
import asyncio
from dotenv import load_dotenv
from telegram import Update, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    PollAnswerHandler,
    ContextTypes,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

QUESTION = "Хотим сосать"
OPTIONS = ["Конечно, нахуй, да", "А когда не сосать?"]

scheduled_jobs = []
poll_id = None
poll_message_id = None
voted_user_ids = set()
user_id_to_name = {}
group_chat_id = None  # <-- динамически определяемый chat_id

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def send_poll(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    global poll_id, poll_message_id, voted_user_ids, user_id_to_name, scheduled_jobs

    voted_user_ids.clear()
    user_id_to_name.clear()
    scheduled_jobs.clear()

    message = await context.bot.send_poll(
        chat_id=chat_id,
        question=QUESTION,
        options=OPTIONS,
        is_anonymous=False,
    )

    poll_id = message.poll.id
    poll_message_id = message.message_id

    job_ping1 = scheduler.add_job(ping_unvoted, "date", run_date=datetime.datetime.now() + datetime.timedelta(minutes=10), args=[context, chat_id])
    job_ping2 = scheduler.add_job(ping_unvoted, "date", run_date=datetime.datetime.now() + datetime.timedelta(minutes=20), args=[context, chat_id])
    job_close = scheduler.add_job(close_poll, "date", run_date=datetime.datetime.now() + datetime.timedelta(minutes=20), args=[context, chat_id])

    scheduled_jobs.extend([job_ping1, job_ping2, job_close])
    logger.info("опсос отправлен")


async def poll_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global group_chat_id
    group_chat_id = update.effective_chat.id

    await send_poll(context, group_chat_id)
    user = update.effective_user
    user_name = f"{user.first_name} {user.last_name or ''}".strip()
    await update.message.reply_text(f"{user_name} предлагает пососать")


async def get_known_user_ids(bot, chat_id):
    members = await bot.get_chat_administrators(chat_id=chat_id)
    return {m.user.id for m in members if not m.user.is_bot}


async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.poll_answer.user
    voted_user_ids.add(user.id)
    user_id_to_name[user.id] = f"{user.first_name} {user.last_name or ''}".strip()
    logger.info(f"{user.first_name} проголосовал")

    if group_chat_id:
        all_user_ids = await get_known_user_ids(context.bot, group_chat_id)
        if all_user_ids and all_user_ids.issubset(voted_user_ids):
            logger.info("Проголосовали все — закрываем опсос досрочно")
            await close_poll(context, group_chat_id, early=True)


async def ping_unvoted(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    all_user_ids = await get_known_user_ids(context.bot, chat_id)
    unvoted = [uid for uid in all_user_ids if uid not in voted_user_ids]

    if unvoted:
        mentions = []
        for uid in unvoted:
            try:
                member = await context.bot.get_chat_member(chat_id=chat_id, user_id=uid)
                user = member.user
                if user.username:
                    mentions.append(f"@{user.username}")
                else:
                    mentions.append(user.first_name)
            except:
                continue

        msg = "Где голос? " + ", ".join(mentions)
        await context.bot.send_message(chat_id=chat_id, text=msg)
        logger.info("Пинг не голосовавших отправлен")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if poll_id is None:
        await update.message.reply_text("Сейчас нет активного опсоса.")
        return

    count = len(voted_user_ids)
    names = ", ".join(user_id_to_name.values()) if user_id_to_name else "ещё никто"
    await update.message.reply_text(f"Проголосовали {count} человек(а): {names}")


async def stop_poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if group_chat_id:
        user = update.effective_user
        user_name = f"{user.first_name} {user.last_name or ''}".strip()
        await close_poll(context, group_chat_id, early=True)
        await update.message.reply_text(f"{user_name} насильно завершает сасание.")


async def close_poll(context: ContextTypes.DEFAULT_TYPE, chat_id: int, early=False):
    global scheduled_jobs

    try:
        await context.bot.stop_poll(chat_id=chat_id, message_id=poll_message_id)
    except Exception as e:
        logger.warning(f"Ошибка при закрытии опсоса: {e}")

    for job in scheduled_jobs:
        try:
            job.remove()
        except:
            pass
    scheduled_jobs.clear()

    all_user_ids = await get_known_user_ids(context.bot, chat_id)

    voted = [user_id_to_name[uid] for uid in voted_user_ids if uid in user_id_to_name]
    not_voted = []
    for uid in all_user_ids:
        if uid not in voted_user_ids:
            try:
                member = await context.bot.get_chat_member(chat_id=chat_id, user_id=uid)
                user = member.user
                not_voted.append(user.first_name)
            except:
                continue

    if not all_user_ids:
        await context.bot.send_message(chat_id=chat_id, text="Сасают все!")
        return

    if len(voted) == len(all_user_ids):
        await context.bot.send_message(chat_id=chat_id, text="Сасают все!")
    else:
        msg = f"Готовы сосать: {', '.join(voted) or 'никто'}\n"
        msg += f"Отказались сосать: {', '.join(not_voted) or 'никто'}"
        await context.bot.send_message(chat_id=chat_id, text=msg)


async def scheduled_poll(context: ContextTypes.DEFAULT_TYPE):
    if group_chat_id:
        await send_poll(context, group_chat_id)
    else:
        logger.warning("Планировщик: chat_id пока не известен, опрос не запущен.")


async def main():
    application = ApplicationBuilder().token(TOKEN).build()

    commands = [
        BotCommand("poll_now", "Запустить опсос прямо сейчас"),
        BotCommand("status", "Показать, кто уже готов сосать"),
        BotCommand("stop_poll", "Остановить опсос насильно"),
    ]
    await application.bot.set_my_commands(commands)

    application.add_handler(CommandHandler("poll_now", poll_now))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("stop_poll", stop_poll))
    application.add_handler(PollAnswerHandler(handle_poll_answer))

    scheduler.add_job(scheduled_poll, "cron", hour=21, minute=0, args=[application.bot])
    scheduler.start()

    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    logger.info("Бот запущен")


if __name__ == "__main__":
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop = asyncio.get_event_loop()

    loop.create_task(main())
    loop.run_forever()
