import logging
import os
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, PollAnswerHandler
import asyncio

import db
import handlers
import scheduler
from poll_state import poll_state
from scheduler import setup_jobs
import web_server

# Load environment variables
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
STEAM_API_KEY = os.getenv("STEAM_API_KEY")

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

def main() -> None:
    """Set up and run the bot."""
    if not TOKEN:
        logger.error("No bot token provided. Set BOT_TOKEN in .env file")
        return

    # Create the Application
    application = Application.builder().token(TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("pol_now", handlers.poll_now_command))
    application.add_handler(CommandHandler("status", handlers.status_command))
    application.add_handler(CommandHandler("stop_poll", handlers.stop_poll))
    application.add_handler(CommandHandler("link_steam", handlers.link_steam_command))
    application.add_handler(CommandHandler("stats", handlers.stats_command))
    application.add_handler(CommandHandler("register_me", handlers.register_me_command))
    application.add_handler(CommandHandler("set_poll_time", handlers.set_poll_time_command))
    application.add_handler(PollAnswerHandler(handlers.handle_poll_answer))

    # Setup database
    db.setup_database()

    # Setup bot commands using post_init
    application.post_init = handlers.setup_commands

    # Запуск веб-сервера для статистики
    application.job_queue.run_once(
        lambda ctx: asyncio.create_task(web_server.start_web_server()),
        0
    )
    logger.info("Scheduled web server startup")

    # Setup the job queue
    application.job_queue.run_once(
        lambda ctx: setup_jobs(
            application.job_queue, 
            handlers.send_poll, 
            STEAM_API_KEY
        ),
        0
    )

    # Start the Bot
    application.run_polling()


if __name__ == "__main__":
    main()
