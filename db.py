import asyncio
import logging
import os
import sys
import traceback
from contextlib import contextmanager
from datetime import datetime, timedelta

from sqlalchemy import create_engine, Column, Integer, String, TIMESTAMP, ForeignKey, Boolean, func, or_
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from exceptions import DatabaseError
from utils import convert_steamid_64_to_32

# Configure logging
logger = logging.getLogger(__name__)

# Constants
DB_FILE = "poll_bot.db"
DATABASE_URL = f"sqlite:///{DB_FILE}"

# SQLAlchemy setup
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# Models
class User(Base):
    __tablename__ = "users"
    telegram_id = Column(String, primary_key=True)
    steam_id = Column(String)
    username = Column(String)
    first_name = Column(String)
    last_name = Column(String)


class Poll(Base):
    __tablename__ = "polls"
    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(String)
    poll_id = Column(String)
    trigger_time = Column(TIMESTAMP)
    end_time = Column(TIMESTAMP)
    trigger_type = Column(String)
    total_votes = Column(Integer, default=0)


class Vote(Base):
    __tablename__ = "votes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    poll_id = Column(Integer, ForeignKey("polls.id"))
    user_id = Column(String)
    option_index = Column(Integer)
    response_time = Column(TIMESTAMP)


class LastActivity(Base):
    __tablename__ = "last_activity"
    chat_id = Column(String, primary_key=True)
    last_poll_end = Column(TIMESTAMP)


class ChatSettings(Base):
    __tablename__ = "chat_settings"
    chat_id = Column(String, primary_key=True)
    poll_time = Column(String, default="15:30")
    chat_name = Column(String)
    paused_polls_count = Column(Integer, default=0)


class UserSteamChat(Base):
    __tablename__ = "user_steam_chats"
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(String)
    steam_id = Column(String)
    chat_id = Column(String)
    created_at = Column(TIMESTAMP, default=datetime.now)


class Match(Base):
    __tablename__ = "matches"
    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String, unique=True, nullable=False)
    chat_id = Column(String, nullable=False)
    winner = Column(String, nullable=False)
    radiant_players = Column(String)
    dire_players = Column(String)
    created_at = Column(TIMESTAMP, default=datetime.now)


class GameParticipant(Base):
    __tablename__ = "game_participants"
    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(String, nullable=False)
    user_id = Column(String, nullable=False)
    poll_end_time = Column(TIMESTAMP, default=datetime.now)


# Global semaphore for database access
db_semaphore = asyncio.Semaphore(1)


def log_error_with_link(error_msg, e):
    """Log error with clickable link to source location"""
    logger.error(f"{error_msg}: {e}")
    tb = traceback.extract_tb(sys.exc_info()[2])
    if tb:
        file, line, _, _ = tb[-1]
        rel_file = os.path.relpath(file)
        logger.error(f"Error location: {rel_file}:{line}")


@contextmanager
def get_db_session():
    """Provide a transactional scope around a series of operations."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        log_error_with_link("Database session error", e)
        raise DatabaseError(e)
    finally:
        session.close()


async def store_user_info(user):
    """Store or update user information in the database"""
    async with db_semaphore:
        with get_db_session() as session:
            db_user = session.query(User).filter(User.telegram_id == str(user.id)).first()
            if db_user:
                db_user.username = user.username
                db_user.first_name = user.first_name
                db_user.last_name = user.last_name
            else:
                db_user = User(
                    telegram_id=str(user.id),
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name,
                )
                session.add(db_user)


async def store_vote(db_poll_id, user_id, option_index):
    """Store vote in the database"""
    async with db_semaphore:
        with get_db_session() as session:
            vote = Vote(
                poll_id=db_poll_id,
                user_id=str(user_id),
                option_index=option_index,
                response_time=datetime.now(),
            )
            session.add(vote)

            poll = session.query(Poll).filter(Poll.id == db_poll_id).first()
            if poll:
                poll.total_votes += 1


async def create_poll_record(chat_id, poll_id, trigger_type):
    """Create a poll record in the database"""
    async with db_semaphore:
        with get_db_session() as session:
            poll = Poll(
                chat_id=str(chat_id),
                poll_id=str(poll_id),
                trigger_time=datetime.now(),
                trigger_type=trigger_type,
            )
            session.add(poll)
            session.flush()
            return poll.id


async def close_poll_record(chat_id, poll_db_id):
    """Update poll record with end time"""
    async with db_semaphore:
        with get_db_session() as session:
            poll = session.query(Poll).filter(Poll.id == poll_db_id).first()
            if poll:
                poll.end_time = datetime.now()

            last_activity = (
                session.query(LastActivity).filter(LastActivity.chat_id == str(chat_id)).first()
            )
            if last_activity:
                last_activity.last_poll_end = datetime.now()
            else:
                last_activity = LastActivity(
                    chat_id=str(chat_id), last_poll_end=datetime.now()
                )
                session.add(last_activity)


async def get_steam_users():
    """Get Steam users with chat IDs"""
    async with db_semaphore:
        with get_db_session() as session:
            steam_users = (
                session.query(User.telegram_id, UserSteamChat.steam_id, User.first_name, UserSteamChat.chat_id)
                .join(UserSteamChat, User.telegram_id == UserSteamChat.telegram_id)
                .filter(UserSteamChat.steam_id.isnot(None))
                .group_by(User.telegram_id, UserSteamChat.chat_id)
                .all()
            )

            if not steam_users:
                # Legacy query for backward compatibility
                steam_users = (
                    session.query(User.telegram_id, User.steam_id, User.first_name, Poll.chat_id)
                    .join(Vote, User.telegram_id == Vote.user_id)
                    .join(Poll, Vote.poll_id == Poll.id)
                    .filter(User.steam_id.isnot(None))
                    .group_by(User.telegram_id, Poll.chat_id)
                    .all()
                )

            last_activities = {
                chat_id: last_poll_end
                for chat_id, last_poll_end in session.query(LastActivity.chat_id, LastActivity.last_poll_end).all()
            }

            return steam_users, last_activities


async def update_user_steam_id(user_id, steam_id, chat_id=None):
    """Update user's Steam ID and optionally link it to a specific chat"""
    async with db_semaphore:
        with get_db_session() as session:
            user = session.query(User).filter(User.telegram_id == str(user_id)).first()
            if user:
                user.steam_id = steam_id

            if chat_id:
                user_steam_chat = (
                    session.query(UserSteamChat)
                    .filter(
                        UserSteamChat.telegram_id == str(user_id),
                        UserSteamChat.chat_id == str(chat_id),
                    )
                    .first()
                )
                if user_steam_chat:
                    user_steam_chat.steam_id = steam_id
                else:
                    user_steam_chat = UserSteamChat(
                        telegram_id=str(user_id),
                        steam_id=steam_id,
                        chat_id=str(chat_id),
                    )
                    session.add(user_steam_chat)
            return True


async def remove_user_steam_id(user_id, chat_id=None):
    """Удаляет Steam ID пользователя из базы данных"""
    async with db_semaphore:
        with get_db_session() as session:
            if chat_id:
                session.query(UserSteamChat).filter(
                    UserSteamChat.telegram_id == str(user_id),
                    UserSteamChat.chat_id == str(chat_id),
                ).delete()
                logger.info(f"Removed Steam ID for user {user_id} in chat {chat_id}")
            else:
                session.query(UserSteamChat).filter(
                    UserSteamChat.telegram_id == str(user_id)
                ).delete()
                user = session.query(User).filter(User.telegram_id == str(user_id)).first()
                if user:
                    user.steam_id = None
                logger.info(f"Removed Steam ID for user {user_id} from all chats")
            return True


async def is_steam_id_linked_to_chat(user_id, chat_id):
    """Проверяет, привязан ли Steam ID пользователя к конкретному чату"""
    async with db_semaphore:
        with get_db_session() as session:
            return (
                session.query(UserSteamChat)
                .filter(
                    UserSteamChat.telegram_id == str(user_id),
                    UserSteamChat.chat_id == str(chat_id),
                )
                .first()
                is not None
            )


async def get_chat_name_by_id(chat_id):
    """Получить название чата по его ID"""
    async with db_semaphore:
        with get_db_session() as session:
            chat_settings = (
                session.query(ChatSettings).filter(ChatSettings.chat_id == str(chat_id)).first()
            )
            return chat_settings.chat_name if chat_settings else None


async def get_known_chat_users(chat_id):
    """Return a set of user IDs known to participate in the given chat."""
    async with db_semaphore:
        with get_db_session() as session:
            users = set()
            votes = (
                session.query(Vote.user_id)
                .join(Poll, Vote.poll_id == Poll.id)
                .filter(Poll.chat_id == str(chat_id))
                .distinct()
                .all()
            )
            users.update(int(row[0]) for row in votes)

            steam_chats = (
                session.query(UserSteamChat.telegram_id)
                .filter(UserSteamChat.chat_id == str(chat_id))
                .distinct()
                .all()
            )
            users.update(int(row[0]) for row in steam_chats)
            return users


async def get_poll_stats(chat_id, poll_options):
    """Get poll statistics for a chat"""
    async with db_semaphore:
        with get_db_session() as session:
            total_polls = (
                session.query(Poll).filter(Poll.chat_id == str(chat_id)).count()
            )

            most_popular_result = (
                session.query(Vote.option_index, func.count(Vote.option_index).label("count"))
                .join(Poll, Vote.poll_id == Poll.id)
                .filter(Poll.chat_id == str(chat_id))
                .group_by(Vote.option_index)
                .order_by(func.count(Vote.option_index).desc())
                .first()
            )

            times = (
                session.query(Poll.trigger_time)
                .filter(Poll.chat_id == str(chat_id))
                .all()
            )

            return {
                "total_polls": total_polls,
                "most_popular": most_popular_result,
                "times": [t[0].strftime("%H:%M") for t in times],
            }


async def set_poll_time(chat_id, poll_time):
    """Set custom poll time for a chat"""
    async with db_semaphore:
        with get_db_session() as session:
            chat_settings = (
                session.query(ChatSettings).filter(ChatSettings.chat_id == str(chat_id)).first()
            )
            if chat_settings:
                chat_settings.poll_time = poll_time
            else:
                chat_settings = ChatSettings(chat_id=str(chat_id), poll_time=poll_time)
                session.add(chat_settings)
            return True


async def remove_poll_time(chat_id):
    """Remove custom poll time for a chat."""
    async with db_semaphore:
        with get_db_session() as session:
            chat_settings = (
                session.query(ChatSettings).filter(ChatSettings.chat_id == str(chat_id)).first()
            )
            if chat_settings:
                session.delete(chat_settings)
            return True


async def get_poll_time(chat_id):
    """Get custom poll time for a chat"""
    async with db_semaphore:
        with get_db_session() as session:
            chat_settings = (
                session.query(ChatSettings).filter(ChatSettings.chat_id == str(chat_id)).first()
            )
            if chat_settings:
                return chat_settings.poll_time
            else:
                chat_settings = ChatSettings(chat_id=str(chat_id))
                session.add(chat_settings)
                return chat_settings.poll_time


async def get_all_chat_poll_times():
    """Get all chat IDs and their custom poll times"""
    async with db_semaphore:
        with get_db_session() as session:
            return {
                chat_id: poll_time
                for chat_id, poll_time in session.query(
                    ChatSettings.chat_id, ChatSettings.poll_time
                ).all()
            }


async def set_paused_polls(chat_id, count):
    """Set the number of polls to pause for a chat."""
    async with db_semaphore:
        with get_db_session() as session:
            chat_settings = (
                session.query(ChatSettings).filter(ChatSettings.chat_id == str(chat_id)).first()
            )
            if chat_settings:
                chat_settings.paused_polls_count = count
            else:
                chat_settings = ChatSettings(chat_id=str(chat_id), paused_polls_count=count)
                session.add(chat_settings)
            return True


async def get_paused_polls(chat_id):
    """Get the number of paused polls for a chat."""
    async with db_semaphore:
        with get_db_session() as session:
            chat_settings = (
                session.query(ChatSettings).filter(ChatSettings.chat_id == str(chat_id)).first()
            )
            return chat_settings.paused_polls_count if chat_settings else 0


async def decrement_paused_polls(chat_id):
    """Decrement the paused polls count for a chat."""
    async with db_semaphore:
        with get_db_session() as session:
            chat_settings = (
                session.query(ChatSettings).filter(ChatSettings.chat_id == str(chat_id)).first()
            )
            if chat_settings and chat_settings.paused_polls_count > 0:
                chat_settings.paused_polls_count -= 1


async def register_user(user):
    """Register a user in the database"""
    await store_user_info(user)
    return True


async def is_user_registered(user_id):
    """Check if a user is registered in the database"""
    async with db_semaphore:
        with get_db_session() as session:
            return (
                session.query(User).filter(User.telegram_id == str(user_id)).first()
                is not None
            )


async def get_user_info(user_id):
    """Get user information by user ID"""
    async with db_semaphore:
        with get_db_session() as session:
            user = session.query(User).filter(User.telegram_id == str(user_id)).first()
            if user:
                return {
                    "telegram_id": user.telegram_id,
                    "username": user.username,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "steam_id": user.steam_id,
                }
            return None


async def set_chat_name(chat_id, chat_name):
    """Сохраняет название чата в базе данных"""
    async with db_semaphore:
        with get_db_session() as session:
            chat_settings = (
                session.query(ChatSettings).filter(ChatSettings.chat_id == str(chat_id)).first()
            )
            if chat_settings:
                chat_settings.chat_name = chat_name
            else:
                chat_settings = ChatSettings(chat_id=str(chat_id), chat_name=chat_name)
                session.add(chat_settings)
            logger.info(f"Saved chat name for chat {chat_id}: {chat_name}")
            return True


async def remove_personal_chat_settings():
    """Удаляет все настройки для личных чатов и очищает все связанные данные"""
    async with db_semaphore:
        with get_db_session() as session:
            personal_chats = (
                session.query(ChatSettings.chat_id)
                .filter(ChatSettings.chat_id.cast(Integer) > 0)
                .all()
            )

            if not personal_chats:
                logger.info("Личных чатов не найдено")
                return True

            logger.info(f"Найдены личные чаты: {personal_chats}")

            for chat_id in personal_chats:
                session.query(Vote).filter(Vote.poll.has(chat_id=chat_id[0])).delete(
                    synchronize_session=False
                )
                session.query(Poll).filter(Poll.chat_id == chat_id[0]).delete(
                    synchronize_session=False
                )
                session.query(ChatSettings).filter(ChatSettings.chat_id == chat_id[0]).delete(
                    synchronize_session=False
                )
                session.query(LastActivity).filter(LastActivity.chat_id == chat_id[0]).delete(
                    synchronize_session=False
                )
                logger.info(f"Удалены данные для личного чата {chat_id[0]}")

            return True


async def store_match(match_id, chat_id, winner, radiant_players, dire_players):
    """Store a match in the database."""
    async with db_semaphore:
        with get_db_session() as session:
            match = Match(
                match_id=match_id,
                chat_id=chat_id,
                winner=winner,
                radiant_players=radiant_players,
                dire_players=dire_players,
            )
            session.add(match)


async def get_games_stats(chat_id, days, user_id=None):
    """Get games statistics for a chat or a user."""
    async with db_semaphore:
        with get_db_session() as session:
            time_filter = datetime.now() - timedelta(days=days)
            if user_id:
                user = session.query(User).filter(User.telegram_id == str(user_id)).first()
                if user and user.steam_id:
                    steam_id_32 = convert_steamid_64_to_32(user.steam_id)
                    return session.query(Match).filter(
                        Match.chat_id == str(chat_id),
                        or_(
                            Match.radiant_players.contains(steam_id_32),
                            Match.dire_players.contains(steam_id_32)
                        ),
                        Match.created_at >= time_filter
                    ).all()
                else:
                    return []
            else:
                return session.query(Match).filter(Match.chat_id == str(chat_id), Match.created_at >= time_filter).all()


async def store_game_participants(chat_id, user_ids):
    """Store game participants in the database."""
    async with db_semaphore:
        with get_db_session() as session:
            for user_id in user_ids:
                participant = GameParticipant(
                    chat_id=chat_id,
                    user_id=user_id,
                )
                session.add(participant)


async def get_game_participants():
    """Get game participants from the database from the last 2 hours."""
    async with db_semaphore:
        with get_db_session() as session:
            time_filter = datetime.now() - timedelta(hours=2)
            participants = session.query(GameParticipant).filter(GameParticipant.poll_end_time >= time_filter).all()
            # Force loading of chat_id before session closes
            for p in participants:
                _ = p.chat_id # Accessing the attribute forces it to load
            return participants


async def delete_game_participants(participant_ids):
    """Delete game participants from the database."""
    async with db_semaphore:
        with get_db_session() as session:
            session.query(GameParticipant).filter(GameParticipant.id.in_(participant_ids)).delete(synchronize_session=False)


async def get_chat_steam_ids_32(chat_id):
    """Get a list of 32-bit Steam IDs for all users in a chat."""
    async with db_semaphore:
        with get_db_session() as session:
            # Query UserSteamChat for all steam_ids linked to the chat_id
            user_steam_chats = session.query(UserSteamChat.steam_id).filter(UserSteamChat.chat_id == str(chat_id)).all()
            steam_ids_64 = [row[0] for row in user_steam_chats if row[0]]

            # Query legacy users as well
            legacy_users = session.query(User.steam_id).join(Vote, User.telegram_id == Vote.user_id).join(Poll, Vote.poll_id == Poll.id).filter(Poll.chat_id == str(chat_id)).filter(User.steam_id.isnot(None)).distinct().all()
            legacy_steam_ids_64 = [row[0] for row in legacy_users if row[0]]

            all_steam_ids_64 = list(set(steam_ids_64 + legacy_steam_ids_64))

            return [convert_steamid_64_to_32(steam_id) for steam_id in all_steam_ids_64]


async def get_match(match_id):
    """Get a match by its ID."""
    async with db_semaphore:
        with get_db_session() as session:
            return session.query(Match).filter(Match.match_id == str(match_id)).first()


async def get_user_info_by_steam_id_32(steam_id_32):
    """Get user information by 32-bit steam ID."""
    async with db_semaphore:
        with get_db_session() as session:
            steam_id_64 = str(int(steam_id_32) + 76561197960265728)
            user = session.query(User).filter(User.steam_id == steam_id_64).first()
            if user:
                return {
                    "telegram_id": user.telegram_id,
                    "username": user.username,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "steam_id": user.steam_id,
                }
            return None