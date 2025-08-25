import asyncio
import logging
from typing import Dict, Set, Optional
from datetime import datetime

import db

# Configure logging
logger = logging.getLogger(__name__)


class PollState:
    def __init__(self):
        self.active_polls: Dict[str, Dict] = {}  # chat_id -> poll data
        self.scheduled_tasks: Dict[str, asyncio.Task] = {}  # chat_id -> task
        self.registered_chats: Set[str] = (
            set()
        )  # Set of chat_ids where the bot has been activated
        self.steam_check_task = None  # Task for checking Steam status

    def is_active(self, chat_id: str) -> bool:
        return chat_id in self.active_polls

    async def create_poll(
        self, chat_id: str, poll_id: str, message_id: int, trigger_type: str
    ) -> None:
        self.active_polls[chat_id] = {
            "poll_id": poll_id,
            "message_id": message_id,
            "votes": {},
            "started_at": datetime.now(),
            "all_users": set(),
            "voted_users": set(),
            "first_ping_sent": False,
            "trigger_type": trigger_type,
            "db_poll_id": None,  # Will be set after DB insert
        }

        # Register this chat for daily polls
        self.registered_chats.add(chat_id)

        # Store poll in database
        self.active_polls[chat_id]["db_poll_id"] = await db.create_poll_record(
            chat_id, poll_id, trigger_type
        )

    async def add_vote(self, poll_id: str, user, option_index: int) -> None:
        for chat_id, poll_data in self.active_polls.items():
            if poll_data["poll_id"] == poll_id:
                poll_data["votes"][user.id] = {"user": user, "option": option_index}
                poll_data["voted_users"].add(user.id)

                # Store user info in database
                await db.store_user_info(user)

                # Store vote in database
                await db.store_vote(poll_data["db_poll_id"], user.id, option_index)

                return

    def get_poll_data(self, chat_id: str) -> Optional[Dict]:
        return self.active_polls.get(chat_id)

    def add_user_to_chat(self, chat_id: str, user_id: int) -> None:
        if chat_id in self.active_polls:
            self.active_polls[chat_id]["all_users"].add(user_id)

    async def close_poll(self, chat_id: str) -> None:
        if chat_id in self.active_polls:
            # Update database with end time
            await db.close_poll_record(
                chat_id, self.active_polls[chat_id]["db_poll_id"]
            )
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

    def set_steam_check_task(self, task) -> None:
        if self.steam_check_task:
            self.steam_check_task.cancel()
        self.steam_check_task = task


# Create a global instance
poll_state = PollState()
