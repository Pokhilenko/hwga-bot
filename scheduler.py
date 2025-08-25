import logging
from datetime import time, datetime, timedelta
import re

import db
from poll_state import poll_state
import steam

# Configure logging
logger = logging.getLogger(__name__)


async def setup_jobs(job_queue, send_poll_func, steam_api_key):
    """Set up scheduled jobs"""

    # Determine if any custom poll times are configured
    chat_times = await db.get_all_chat_poll_times()

    if not chat_times:
        # No custom schedules - run default poll at 21:30 (GMT+6)
        target_time = time(hour=15, minute=30)  # 21:30 GMT+6 = 15:30 UTC
        job_queue.run_daily(
            lambda ctx: daily_poll(ctx, send_poll_func),
            time=target_time,
            days=(0, 1, 2, 3, 4, 5, 6),
        )
    else:
        # Set up custom poll times for each chat
        await setup_custom_poll_times(job_queue, send_poll_func, chat_times)

    # Set up Steam status checker - run hourly
    steam_check_job = job_queue.run_repeating(
        lambda ctx: steam.check_steam_status(ctx, steam_api_key, send_poll_func),
        interval=60 * 60,  # Check every hour
        first=0,  # Start immediately
    )

    # Store the job reference
    poll_state.set_steam_check_task(steam_check_job)

    logger.info("Scheduled jobs set up successfully")


async def setup_custom_poll_times(job_queue, send_poll_func, chat_times):
    """Set up custom poll times for each chat"""
    # chat_times is a mapping of chat_id -> poll time in UTC

    for chat_id, poll_time_str in chat_times.items():
        try:
            # Parse the time string (format: "HH:MM" in UTC)
            hour, minute = map(int, poll_time_str.split(":"))
            target_time = time(hour=hour, minute=minute)

            # Schedule the job
            job_queue.run_daily(
                lambda ctx, chat=chat_id: custom_poll(ctx, send_poll_func, chat),
                time=target_time,
                days=(0, 1, 2, 3, 4, 5, 6),  # Run every day
                name=f"custom_poll_{chat_id}_{poll_time_str}",
            )

            logger.info(
                f"Scheduled custom poll for chat {chat_id} at {poll_time_str} UTC"
            )
        except Exception as e:
            logger.error(f"Error scheduling custom poll for chat {chat_id}: {e}")


async def parse_time_string(time_str):
    """Parse a time string in various formats to UTC time"""
    # Remove any whitespace
    time_str = time_str.strip().lower()

    # Try 24-hour format: "HH:MM"
    match = re.match(r"^(\d{1,2}):(\d{2})$", time_str)
    if match:
        hour, minute = map(int, match.groups())
        if 0 <= hour < 24 and 0 <= minute < 60:
            # Convert from GMT+6 to UTC
            dt = datetime.now().replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            dt -= timedelta(hours=6)  # Adjust for GMT+6
            return f"{dt.hour:02d}:{dt.minute:02d}"

    # Try 12-hour format: "HH:MM AM/PM"
    match = re.match(r"^(\d{1,2}):(\d{2})\s*(am|pm)$", time_str)
    if match:
        hour, minute, period = match.groups()
        hour = int(hour)
        minute = int(minute)

        # Validate
        if not (1 <= hour <= 12 and 0 <= minute < 60):
            return None

        # Convert to 24-hour
        if period == "pm" and hour < 12:
            hour += 12
        elif period == "am" and hour == 12:
            hour = 0

        # Convert from GMT+6 to UTC
        dt = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
        dt -= timedelta(hours=6)  # Adjust for GMT+6
        return f"{dt.hour:02d}:{dt.minute:02d}"

    return None  # Invalid format


async def daily_poll(context, send_poll_func):
    """Send daily polls to all registered chats."""
    registered_chats = poll_state.get_registered_chats()

    logger.info(
        f"Running daily poll for {len(registered_chats)} chats at {datetime.now()}"
    )

    for chat_id in registered_chats:
        if not poll_state.is_active(chat_id):
            await send_poll_func(chat_id, context, "Ah shit, here we go again!")


async def custom_poll(context, send_poll_func, chat_id):
    """Send custom poll for a specific chat at the configured time."""
    logger.info(f"Running custom poll for chat {chat_id} at {datetime.now()}")

    if not poll_state.is_active(chat_id):
        await send_poll_func(
            chat_id, context, "Ah shit, here we go again! (Custom time poll)"
        )


async def reschedule_poll_for_chat(job_queue, chat_id, send_poll_func):
    """Reschedule the poll for a chat based on its stored time."""
    # Remove existing scheduled jobs for this chat
    for job in job_queue.jobs():
        if job.name and job.name.startswith(f"custom_poll_{chat_id}_"):
            job.schedule_removal()
            logger.info(f"Removed existing poll job for chat {chat_id}")

    # Get the new poll time
    poll_time_str = await db.get_poll_time(chat_id)

    try:
        # Parse the time string (format: "HH:MM" in UTC)
        hour, minute = map(int, poll_time_str.split(":"))
        target_time = time(hour=hour, minute=minute)

        # Schedule the job
        job_queue.run_daily(
            lambda ctx, chat=chat_id: custom_poll(ctx, send_poll_func, chat),
            time=target_time,
            days=(0, 1, 2, 3, 4, 5, 6),  # Run every day
            name=f"custom_poll_{chat_id}_{poll_time_str}",
        )

        logger.info(
            f"Rescheduled custom poll for chat {chat_id} at {poll_time_str} UTC"
        )
        return True
    except Exception as e:
        logger.error(f"Error rescheduling custom poll for chat {chat_id}: {e}")
        return False
