import datetime
import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, PollAnswerHandler, CallbackContext

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

bot = Bot(token=TOKEN)
updater = Updater(token=TOKEN, use_context=True)
dispatcher = updater.dispatcher

poll_id = None
poll_message_id = None
voted_user_ids = set()
user_id_to_name = {}
scheduler = BackgroundScheduler()

QUESTION = "Хотим сосать"
OPTIONS = ["Конечно, нахуй, да", "А когда не сосать?"]

logging.basicConfig(level=logging.INFO)


def send_poll():
    global poll_id, poll_message_id, voted_user_ids, user_id_to_name
    voted_user_ids.clear()
    user_id_to_name.clear()

    message = bot.send_poll(
        chat_id=CHAT_ID,
        question=QUESTION,
        options=OPTIONS,
        is_anonymous=False
    )
    poll_id = message.poll.id
    poll_message_id = message.message_id

    scheduler.add_job(ping_unvoted, 'date', run_date=datetime.datetime.now() + datetime.timedelta(minutes=30))
    scheduler.add_job(close_poll, 'date', run_date=datetime.datetime.now() + datetime.timedelta(minutes=60))


def handle_poll_answer(update: Update, context: CallbackContext):
    user = update.poll_answer.user
    voted_user_ids.add(user.id)
    user_id_to_name[user.id] = f"{user.first_name} {user.last_name or ''}".strip()


def ping_unvoted():
    mentions = "@все, кто не проголосовал"
    bot.send_message(chat_id=CHAT_ID, text=f"Где голос? {mentions}")


def close_poll():
    try:
        bot.stop_poll(chat_id=CHAT_ID, message_id=poll_message_id)
    except:
        pass

    if not user_id_to_name:
        bot.send_message(chat_id=CHAT_ID, text="Сегодня никто не сосёт...")
    elif len(voted_user_ids) >= 2:
        names = ", ".join(user_id_to_name.values())
        bot.send_message(chat_id=CHAT_ID, text=f"Сегодня сосут: {names}")
    else:
        bot.send_message(chat_id=CHAT_ID, text="Сасают все!")


def poll_now(update: Update, context: CallbackContext):
    send_poll()
    context.bot.send_message(chat_id=CHAT_ID, text="Опрос отправлен вручную!")


def main():
    dispatcher.add_handler(CommandHandler("poll_now", poll_now))
    dispatcher.add_handler(PollAnswerHandler(handle_poll_answer))

    scheduler.add_job(send_poll, 'cron', hour=21, minute=0)
    scheduler.start()

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
