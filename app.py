import asyncio
import logging
import os
import random
from dotenv import load_dotenv
from datetime import datetime, time
from typing import Dict, Set, Optional

from telegram import Update, User
from telegram.ext import Application, CommandHandler, PollAnswerHandler, ContextTypes
from telegram.error import BadRequest

load_dotenv()

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
TOKEN = os.getenv('BOT_TOKEN')
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


# Poll state tracking
class PollState:
    def __init__(self):
        self.active_polls: Dict[str, Dict] = {}  # chat_id -> poll data
        self.scheduled_tasks: Dict[str, asyncio.Task] = {}  # chat_id -> task
        self.registered_chats: Set[str] = set()  # Set of chat_ids where the bot has been activated

    def is_active(self, chat_id: str) -> bool:
        return chat_id in self.active_polls

    def create_poll(self, chat_id: str, poll_id: str, message_id: int) -> None:
        self.active_polls[chat_id] = {
            "poll_id": poll_id,
            "message_id": message_id,
            "votes": {},
            "started_at": datetime.now(),
            "all_users": set(),
            "voted_users": set(),
            "first_ping_sent": False,
        }

        # Register this chat for daily polls
        self.registered_chats.add(chat_id)

    def add_vote(self, poll_id: str, user: User, option_index: int) -> None:
        for chat_id, poll_data in self.active_polls.items():
            if poll_data["poll_id"] == poll_id:
                poll_data["votes"][user.id] = {
                    "user": user,
                    "option": option_index
                }
                poll_data["voted_users"].add(user.id)
                return

    def get_poll_data(self, chat_id: str) -> Optional[Dict]:
        return self.active_polls.get(chat_id)

    def add_user_to_chat(self, chat_id: str, user_id: int) -> None:
        if chat_id in self.active_polls:
            self.active_polls[chat_id]["all_users"].add(user_id)

    def close_poll(self, chat_id: str) -> None:
        if chat_id in self.active_polls:
            del self.active_polls[chat_id]

        # Cancel any running tasks for this chat
        if chat_id in self.scheduled_tasks:
            self.scheduled_tasks[chat_id].cancel()
            del self.scheduled_tasks[chat_id]

    def set_task(self, chat_id: str, task: asyncio.Task) -> None:
        # Cancel existing task if any
        if chat_id in self.scheduled_tasks:
            self.scheduled_tasks[chat_id].cancel()

        self.scheduled_tasks[chat_id] = task

    def register_chat(self, chat_id: str) -> None:
        self.registered_chats.add(chat_id)

    def get_registered_chats(self) -> Set[str]:
        return self.registered_chats


# Initialize poll state
poll_state = PollState()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    chat_id = str(update.effective_chat.id)

    # Register this chat for daily polls
    poll_state.register_chat(chat_id)

    await update.message.reply_text(
        "Привет! Я бот для опросов.\n"
        "/poll_now - начать опрос вручную\n"
        "/status - проверить статус текущего опроса\n"
        "/stop_poll - остановить текущий опрос"
    )


async def poll_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a new poll manually."""
    chat_id = str(update.effective_chat.id)
    user = update.effective_user

    # Check if there's already an active poll
    if poll_state.is_active(chat_id):
        await update.message.reply_text("Опрос уже активен.")
        return

    # Leading message for manual poll
    message = f"{user.first_name} приглашает всех на посасать!"
    await send_poll(chat_id, context, message, manual=True)


async def stop_poll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manually stop the current poll."""
    chat_id = str(update.effective_chat.id)

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


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check the status of the current poll."""
    chat_id = str(update.effective_chat.id)

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


async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle when a user answers the poll."""
    answer = update.poll_answer
    poll_id = answer.poll_id
    user = update.effective_user
    selected_option = answer.option_ids[0] if answer.option_ids else None

    # Record this vote
    if selected_option is not None:
        poll_state.add_vote(poll_id, user, selected_option)

    # Check if all users have voted
    for chat_id, poll_data in poll_state.active_polls.items():
        if poll_data["poll_id"] == poll_id:
            if poll_data["all_users"] and poll_data["all_users"].issubset(poll_data["voted_users"]):
                await process_poll_results(chat_id, context)
            break


async def send_poll(chat_id: str, context: ContextTypes.DEFAULT_TYPE,
                    message: str, manual: bool = False) -> None:
    """Send a poll to the specified chat."""
    # Send the leading message
    await context.bot.send_message(chat_id=chat_id, text=message)

    # Send the actual poll
    message = await context.bot.send_poll(
        chat_id=chat_id,
        question=POLL_QUESTION,
        options=POLL_OPTIONS,
        is_anonymous=False,
    )

    # Store poll information
    poll_id = message.poll.id
    message_id = message.message_id
    poll_state.create_poll(chat_id, poll_id, message_id)

    # Get chat members to track who needs to vote
    try:
        chat_members = await context.bot.get_chat_administrators(chat_id)
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


async def send_reminder(chat_id: str, context: ContextTypes.DEFAULT_TYPE, delay: int) -> None:
    """Send a reminder to non-voters after a delay."""
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
        ping_message += f"@{user_id} "

    if ping_message:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Напоминание о голосовании: {ping_message}"
        )


async def close_poll_after_timeout(chat_id: str, context: ContextTypes.DEFAULT_TYPE, delay: int) -> None:
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


async def process_poll_results(chat_id: str, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        result_message = f"Пока что никто не готов сасать, повторим опрос через {deferred_delay} минут"
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
        result_message += f"\nНе прогосоловали: {', '.join([str(uid) for uid in non_voted])}"

    # Send result message
    await context.bot.send_message(chat_id=chat_id, text=result_message)

    # Close the poll in our state
    poll_state.close_poll(chat_id)

    # Schedule a new poll if needed
    if deferred_delay is not None:
        delay_task = context.application.create_task(
            schedule_new_poll(chat_id, context, deferred_delay * 60)
        )
        poll_state.set_task(chat_id, delay_task)


async def schedule_new_poll(chat_id: str, context: ContextTypes.DEFAULT_TYPE, delay: int) -> None:
    """Schedule a new poll after the specified delay."""
    await asyncio.sleep(delay)
    await send_poll(chat_id, context, "Ah shit, here we go again!")


async def daily_poll(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send daily polls to all registered chats."""
    registered_chats = poll_state.get_registered_chats()

    for chat_id in registered_chats:
        if not poll_state.is_active(chat_id):
            await send_poll(chat_id, context, "Ah shit, here we go again!")


def main() -> None:
    """Set up and run the bot."""
    # Create the Application
    application = Application.builder().token(TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("poll_now", poll_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("stop_poll", stop_poll))
    application.add_handler(PollAnswerHandler(handle_poll_answer))

    # Set up the daily job (at 21:45)
    job_queue = application.job_queue
    job_queue.run_daily(
        daily_poll,
        time=time(hour=21, minute=45, second=0)
    )

    # Start the Bot
    application.run_polling()


if __name__ == "__main__":
    main()