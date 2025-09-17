import logging
import os
import asyncio
from dotenv import load_dotenv

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    PollAnswerHandler,
    CallbackQueryHandler,
)

import handlers
from scheduler import setup_jobs
import web_server

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def main():
    """Main function to start the bot."""

    # Load environment variables from .env file
    load_dotenv()
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN:
        logger.critical("BOT_TOKEN environment variable not set. The bot cannot start.")
        return

    STEAM_API_KEY = os.getenv("STEAM_API_KEY")
    if not STEAM_API_KEY:
        logger.warning("STEAM_API_KEY environment variable not set. Steam-related features will not work.")

    # Create the Telegram Application
    application = ApplicationBuilder().token(TOKEN).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("poll_now", handlers.poll_now_command))
    application.add_handler(CommandHandler("status", handlers.status_command))
    application.add_handler(CommandHandler("stop_poll", handlers.stop_poll))
    application.add_handler(CommandHandler("stats", handlers.stats_command))
    application.add_handler(
        CommandHandler("set_poll_time", handlers.set_poll_time_command)
    )
    application.add_handler(
        CommandHandler("get_poll_time", handlers.get_poll_time_command)
    )
    application.add_handler(CommandHandler("pause_polls", handlers.pause_polls_command))

    # Register Steam-related command handlers
    application.add_handler(CommandHandler("link_steam", handlers.link_steam_command))
    application.add_handler(
        CommandHandler("unlink_steam", handlers.unlink_steam_command)
    )
    application.add_handler(
        CommandHandler("who_is_playing", handlers.who_is_playing_command)
    )
    application.add_handler(CommandHandler("games_stat", handlers.games_stat_command))

    # Register callback query handlers
    application.add_handler(
        CallbackQueryHandler(
            handlers.handle_unlink_steam_confirm, pattern="^unlink_confirm:"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            handlers.handle_unlink_steam_cancel, pattern="^unlink_cancel:"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            handlers.refresh_games_stat_command, pattern="^refresh_games_stat:"
        )
    )

    # Register poll answer handler
    application.add_handler(PollAnswerHandler(handlers.handle_poll_answer))

    # Set up bot commands to be suggested in the Telegram UI
    application.post_init = handlers.setup_commands

    # Schedule the web server to start
    application.job_queue.run_once(
        lambda ctx: asyncio.create_task(web_server.start_web_server()), 0
    )
    logger.info("Scheduled web server startup")

    # Set up the job queue for sending polls and checking Steam status
    application.job_queue.run_once(
        lambda ctx: asyncio.create_task(
            setup_jobs(application.job_queue, handlers.send_poll, STEAM_API_KEY)
        ),
        0,
    )
    logger.info("Scheduled job queue setup")

    # Start the bot
    logger.info("Starting bot")
    application.run_polling()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Error in main thread: {e}", exc_info=True)