import logging
import os
import asyncio
from dotenv import load_dotenv

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    PollAnswerHandler,
    CallbackQueryHandler,
    ConversationHandler,
)

import db
import handlers
import scheduler
from poll_state import poll_state
from scheduler import setup_jobs
import web_server
import steam

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    """Main function to start the bot."""
    # Setup database
    db.setup_database()

    # Load environment variables
    load_dotenv()
    TOKEN = os.getenv("BOT_TOKEN")
    STEAM_API_KEY = os.getenv("STEAM_API_KEY")

    # Setup telegram app with token
    application = ApplicationBuilder().token(TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("pol_now", handlers.poll_now_command))
    application.add_handler(CommandHandler("status", handlers.status_command))
    application.add_handler(CommandHandler("stop_poll", handlers.stop_poll))
    application.add_handler(CommandHandler("stats", handlers.stats_command))
    application.add_handler(CommandHandler("set_poll_time", handlers.set_poll_time_command))
    application.add_handler(CommandHandler("get_poll_time", handlers.get_poll_time_command))
    
    # Steam related commands
    application.add_handler(CommandHandler("link_steam", handlers.link_steam_command))
    application.add_handler(CommandHandler("unlink_steam", handlers.unlink_steam_command))
    application.add_handler(CommandHandler("who_is_playing", handlers.who_is_playing_command))

    # Text messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message))
    
    # Callback query handlers
    application.add_handler(CallbackQueryHandler(handlers.handle_unlink_steam_confirm, pattern="^unlink_confirm:"))
    application.add_handler(CallbackQueryHandler(handlers.handle_unlink_steam_cancel, pattern="^unlink_cancel:"))

    # Add handlers for poll answers
    application.add_handler(PollAnswerHandler(handlers.handle_poll_answer))

    # Setup bot commands using post_init
    application.post_init = handlers.setup_commands

    # Запуск веб-сервера для статистики
    application.job_queue.run_once(
        lambda ctx: asyncio.create_task(web_server.start_web_server()),
        0
    )
    logger.info("Scheduled web server startup")

    # Set up the job queue
    application.job_queue.run_once(
        lambda ctx: asyncio.create_task(setup_jobs(application.job_queue, handlers.send_poll, STEAM_API_KEY)),
        0
    )
    logger.info("Scheduled job queue setup")

    # Start the Bot
    logger.info("Starting bot")
    application.run_polling()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Error in main thread: {e}", exc_info=True)
