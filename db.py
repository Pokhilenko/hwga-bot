import asyncio
import logging
import sqlite3
from datetime import datetime, time
import os
import time as time_module
from contextlib import contextmanager
import traceback
import sys

# Configure logging
logger = logging.getLogger(__name__)

# Constants
DB_FILE = 'poll_bot.db'

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
def safe_db_connect(timeout=5.0):
    """Safely connect to the database with error handling"""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=timeout)
        yield conn
    except sqlite3.Error as e:
        log_error_with_link("Database connection error", e)
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            try:
                conn.close()
            except Exception as e:
                log_error_with_link("Error closing database connection", e)

def setup_database():
    """Create database tables if they don't exist"""
    db_exists = os.path.exists(DB_FILE)
    create_tables = not db_exists
    
    # Проверяем, нужно ли обновить схему базы данных
    if db_exists:
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            
            # Check for users table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            if not cursor.fetchone():
                create_tables = True
            
            # Check if last_activity table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='last_activity'")
            if not cursor.fetchone():
                create_tables = True
                
            # Check if chat_settings table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_settings'")
            if not cursor.fetchone():
                create_tables = True
            
            # Check if user_steam_chats table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_steam_chats'")
            if not cursor.fetchone():
                # Новая таблица с апреля 2025 года - нужно создать
                create_tables = True
                
            conn.close()
        except Exception as e:
            logger.error(f"Error checking database schema: {e}")
            create_tables = True
    
    # Создаем новую базу данных или обновляем существующую
    if not db_exists or create_tables:
        logger.info("Creating or updating database tables")
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()

            # Users table - Store Telegram and Steam ID mappings
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                telegram_id TEXT PRIMARY KEY,
                steam_id TEXT,
                username TEXT,
                first_name TEXT,
                last_name TEXT
            )
            ''')

            # Poll results table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS polls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT,
                poll_id TEXT,
                trigger_time TIMESTAMP,
                end_time TIMESTAMP,
                trigger_type TEXT,
                total_votes INTEGER DEFAULT 0
            )
            ''')

            # Votes table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                poll_id INTEGER,
                user_id TEXT,
                option_index INTEGER,
                response_time TIMESTAMP,
                FOREIGN KEY (poll_id) REFERENCES polls(id)
            )
            ''')

            # Last activity tracking for Steam integration
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS last_activity (
                chat_id TEXT PRIMARY KEY,
                last_poll_end TIMESTAMP
            )
            ''')
            
            # Chat settings for poll time
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_settings (
                chat_id TEXT PRIMARY KEY,
                poll_time TEXT DEFAULT '15:30',  -- Default is 21:30 GMT+6 (15:30 UTC)
                chat_name TEXT
            )
            ''')
            
            # New table for tracking Steam IDs by chat
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_steam_chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id TEXT,
                steam_id TEXT,
                chat_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(telegram_id, chat_id)
            )
            ''')

            conn.commit()
            conn.close()
            logger.info("Database tables created or updated successfully")
        except Exception as e:
            logger.error(f"Error creating database tables: {e}")

async def store_user_info(user):
    """Store or update user information in the database"""
    async with db_semaphore:
        try:
            with safe_db_connect() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                INSERT OR REPLACE INTO users (telegram_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
                ''', (user.id, user.username, user.first_name, user.last_name))
                conn.commit()
        except Exception as e:
            log_error_with_link("Database error in store_user_info", e)

async def store_vote(db_poll_id, user_id, option_index):
    """Store vote in the database"""
    async with db_semaphore:
        try:
            with safe_db_connect() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                INSERT INTO votes (poll_id, user_id, option_index, response_time)
                VALUES (?, ?, ?, ?)
                ''', (db_poll_id, user_id, option_index, datetime.now()))

                # Update total votes count in polls table
                cursor.execute('''
                UPDATE polls SET total_votes = total_votes + 1 WHERE id = ?
                ''', (db_poll_id,))

                conn.commit()
        except Exception as e:
            log_error_with_link("Database error in store_vote", e)

async def create_poll_record(chat_id, poll_id, trigger_type):
    """Create a poll record in the database"""
    async with db_semaphore:
        poll_db_id = None
        try:
            with safe_db_connect() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                INSERT INTO polls (chat_id, poll_id, trigger_time, trigger_type)
                VALUES (?, ?, ?, ?)
                ''', (chat_id, poll_id, datetime.now(), trigger_type))

                # Get the poll ID from the database
                poll_db_id = cursor.lastrowid
                conn.commit()
        except Exception as e:
            log_error_with_link("Database error in create_poll_record", e)
        
        return poll_db_id

async def close_poll_record(chat_id, poll_db_id):
    """Update poll record with end time"""
    async with db_semaphore:
        try:
            with safe_db_connect() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                UPDATE polls SET end_time = ? WHERE id = ?
                ''', (datetime.now(), poll_db_id))

                # Update last activity for this chat
                cursor.execute('''
                INSERT OR REPLACE INTO last_activity (chat_id, last_poll_end)
                VALUES (?, ?)
                ''', (chat_id, datetime.now()))

                conn.commit()
        except Exception as e:
            log_error_with_link("Database error in close_poll_record", e)

async def get_steam_users():
    """Get Steam users with chat IDs"""
    async with db_semaphore:
        try:
            with safe_db_connect() as conn:
                cursor = conn.cursor()
                # Получаем пользователей из таблицы связей Steam ID с чатами
                cursor.execute('''
                SELECT u.telegram_id, usc.steam_id, u.first_name, usc.chat_id 
                FROM user_steam_chats usc
                JOIN users u ON usc.telegram_id = u.telegram_id
                WHERE usc.steam_id IS NOT NULL
                GROUP BY u.telegram_id, usc.chat_id
                ''')
                
                # Если в таблице связей пусто, используем старый метод для обратной совместимости
                steam_users = cursor.fetchall()
                if not steam_users:
                    # Legacy query for backward compatibility
                    cursor.execute('''
                    SELECT DISTINCT u.telegram_id, u.steam_id, u.first_name, p.chat_id 
                    FROM users u
                    JOIN polls p ON EXISTS (
                        SELECT 1 FROM votes v 
                        WHERE v.poll_id = p.id AND v.user_id = u.telegram_id
                    )
                    WHERE u.steam_id IS NOT NULL
                    GROUP BY u.telegram_id, p.chat_id
                    ''')
                    steam_users = cursor.fetchall()
                
                # Get last poll activity by chat
                cursor.execute('''
                SELECT chat_id, last_poll_end
                FROM last_activity
                ''')
                
                last_activities = {chat_id: last_poll_end for chat_id, last_poll_end in cursor.fetchall()}
                
                result = (steam_users, last_activities)
        except Exception as e:
            log_error_with_link("Database error in get_steam_users", e)
            result = ([], {})
            
        return result

async def update_user_steam_id(user_id, steam_id, chat_id=None):
    """Update user's Steam ID and optionally link it to a specific chat"""
    async with db_semaphore:
        success = False
        try:
            with safe_db_connect() as conn:
                cursor = conn.cursor()
                # Update global Steam ID
                cursor.execute("""
                UPDATE users SET steam_id = ? WHERE telegram_id = ?
                """, (steam_id, user_id))
                
                # If chat_id provided, link the Steam ID to this chat
                if chat_id:
                    cursor.execute("""
                    INSERT OR REPLACE INTO user_steam_chats (telegram_id, steam_id, chat_id)
                    VALUES (?, ?, ?)
                    """, (user_id, steam_id, chat_id))
                
                conn.commit()
                success = True
        except Exception as e:
            log_error_with_link("Database error in update_user_steam_id", e)
            
        return success

async def remove_user_steam_id(user_id, chat_id=None):
    """Удаляет Steam ID пользователя из базы данных"""
    async with db_semaphore:
        success = False
        try:
            with safe_db_connect() as conn:
                cursor = conn.cursor()
                
                if chat_id:
                    # Remove Steam ID only for specific chat
                    cursor.execute("""
                    DELETE FROM user_steam_chats WHERE telegram_id = ? AND chat_id = ?
                    """, (user_id, chat_id))
                    success = True
                    logger.info(f"Removed Steam ID for user {user_id} in chat {chat_id}")
                else:
                    # Remove from all chats and global Steam ID
                    cursor.execute("""
                    DELETE FROM user_steam_chats WHERE telegram_id = ?
                    """, (user_id,))
                    
                    cursor.execute("""
                    UPDATE users SET steam_id = NULL WHERE telegram_id = ?
                    """, (user_id,))
                    
                    success = True
                    logger.info(f"Removed Steam ID for user {user_id} from all chats")
                
                conn.commit()
        except Exception as e:
            log_error_with_link("Database error in remove_user_steam_id", e)
            
        return success

async def is_steam_id_linked_to_chat(user_id, chat_id):
    """Проверяет, привязан ли Steam ID пользователя к конкретному чату"""
    async with db_semaphore:
        is_linked = False
        try:
            with safe_db_connect() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT 1 FROM user_steam_chats 
                WHERE telegram_id = ? AND chat_id = ?
                """, (user_id, chat_id))
                
                is_linked = cursor.fetchone() is not None
        except Exception as e:
            log_error_with_link("Database error in is_steam_id_linked_to_chat", e)
            
        return is_linked

async def get_chat_name_by_id(chat_id):
    """Получить название чата по его ID"""
    async with db_semaphore:
        chat_name = None
        try:
            with safe_db_connect() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT chat_name FROM chat_settings 
                WHERE chat_id = ?
                """, (chat_id,))
                
                result = cursor.fetchone()
                if result:
                    chat_name = result[0]
        except Exception as e:
            log_error_with_link("Database error in get_chat_name_by_id", e)

        return chat_name

async def get_known_chat_users(chat_id):
    """Return a set of user IDs known to participate in the given chat."""
    async with db_semaphore:
        users = set()
        try:
            with safe_db_connect() as conn:
                cursor = conn.cursor()

                # Users who have voted in previous polls
                cursor.execute(
                    """
                    SELECT DISTINCT v.user_id
                    FROM votes v
                    JOIN polls p ON v.poll_id = p.id
                    WHERE p.chat_id = ?
                    """,
                    (chat_id,),
                )
                users.update(int(row[0]) for row in cursor.fetchall())

                # Users linked via Steam to this chat
                cursor.execute(
                    """
                    SELECT DISTINCT telegram_id
                    FROM user_steam_chats
                    WHERE chat_id = ?
                    """,
                    (chat_id,),
                )
                users.update(int(row[0]) for row in cursor.fetchall())
        except Exception as e:
            log_error_with_link("Database error in get_known_chat_users", e)

        return users

async def get_poll_stats(chat_id, poll_options):
    """Get poll statistics for a chat"""
    async with db_semaphore:
        try:
            with safe_db_connect() as conn:
                cursor = conn.cursor()
                # Get total number of polls
                cursor.execute("SELECT COUNT(*) FROM polls WHERE chat_id = ?", (chat_id,))
                total_polls = cursor.fetchone()[0]

                # Get most popular option
                cursor.execute("""
                SELECT option_index, COUNT(*) as count 
                FROM votes v
                JOIN polls p ON v.poll_id = p.id
                WHERE p.chat_id = ?
                GROUP BY option_index
                ORDER BY count DESC
                LIMIT 1
                """, (chat_id,))

                most_popular_result = cursor.fetchone()
                most_popular_option = None
                if most_popular_result:
                    option_index, count = most_popular_result
                    most_popular_option = (option_index, count)

                # Get average poll trigger time (in GMT+6)
                cursor.execute("""
                SELECT strftime('%H:%M', trigger_time, '+6 hours') as hour_minute
                FROM polls
                WHERE chat_id = ?
                """, (chat_id,))

                times = cursor.fetchall()
                
                result = {
                    'total_polls': total_polls,
                    'most_popular': most_popular_option,
                    'times': times
                }
        except Exception as e:
            log_error_with_link("Database error in get_poll_stats", e)
            result = {
                'total_polls': 0,
                'most_popular': None,
                'times': []
            }
            
        return result

async def set_poll_time(chat_id, poll_time):
    """Set custom poll time for a chat"""
    async with db_semaphore:
        success = False
        try:
            with safe_db_connect() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                INSERT OR REPLACE INTO chat_settings (chat_id, poll_time)
                VALUES (?, ?)
                ''', (chat_id, poll_time))
                
                conn.commit()
                success = True
        except Exception as e:
            log_error_with_link("Database error in set_poll_time", e)
            
        return success

async def get_poll_time(chat_id):
    """Get custom poll time for a chat"""
    async with db_semaphore:
        try:
            with safe_db_connect() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                SELECT poll_time FROM chat_settings WHERE chat_id = ?
                ''', (chat_id,))
                
                result = cursor.fetchone()
                if result:
                    poll_time = result[0]
                else:
                    # Default time: 21:30 GMT+6 = 15:30 UTC
                    poll_time = "15:30"
                    
                    # Insert default time
                    cursor.execute('''
                    INSERT OR REPLACE INTO chat_settings (chat_id, poll_time)
                    VALUES (?, ?)
                    ''', (chat_id, poll_time))
                    conn.commit()
        except Exception as e:
            log_error_with_link("Database error in get_poll_time", e)
            poll_time = "15:30"  # Default if error
            
        return poll_time

async def get_all_chat_poll_times():
    """Get all chat IDs and their custom poll times"""
    async with db_semaphore:
        chat_times = {}
        try:
            with safe_db_connect() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT chat_id, poll_time FROM chat_settings')
                chat_times = {chat_id: poll_time for chat_id, poll_time in cursor.fetchall()}
        except Exception as e:
            log_error_with_link("Database error in get_all_chat_poll_times", e)
            
        return chat_times

async def register_user(user):
    """Register a user in the database"""
    # This is just an alias to store_user_info
    await store_user_info(user)
    return True

async def is_user_registered(user_id):
    """Check if a user is registered in the database"""
    async with db_semaphore:
        exists = False
        try:
            with safe_db_connect() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT 1 FROM users WHERE telegram_id = ?', (user_id,))
                exists = cursor.fetchone() is not None
        except Exception as e:
            log_error_with_link("Database error in is_user_registered", e)
            
        return exists

async def get_user_info(user_id):
    """Get user information by user ID"""
    async with db_semaphore:
        user_info = None
        try:
            with safe_db_connect() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                SELECT telegram_id, username, first_name, last_name, steam_id
                FROM users
                WHERE telegram_id = ?
                ''', (user_id,))
                result = cursor.fetchone()
                if result:
                    user_info = {
                        'telegram_id': result[0],
                        'username': result[1],
                        'first_name': result[2],
                        'last_name': result[3],
                        'steam_id': result[4]
                    }
        except Exception as e:
            log_error_with_link("Database error in get_user_info", e)
            
        return user_info

async def set_chat_name(chat_id, chat_name):
    """Сохраняет название чата в базе данных"""
    async with db_semaphore:
        success = False
        try:
            with safe_db_connect() as conn:
                cursor = conn.cursor()
                
                # Проверяем, существует ли запись для этого чата
                cursor.execute('''
                SELECT 1 FROM chat_settings WHERE chat_id = ?
                ''', (chat_id,))
                
                if cursor.fetchone():
                    # Обновляем название чата
                    cursor.execute('''
                    UPDATE chat_settings SET chat_name = ? WHERE chat_id = ?
                    ''', (chat_name, chat_id))
                else:
                    # Создаем новую запись
                    cursor.execute('''
                    INSERT INTO chat_settings (chat_id, chat_name)
                    VALUES (?, ?)
                    ''', (chat_id, chat_name))
                
                conn.commit()
                success = True
                logger.info(f"Saved chat name for chat {chat_id}: {chat_name}")
        except Exception as e:
            log_error_with_link("Database error in set_chat_name", e)
            
        return success

async def remove_personal_chat_settings():
    """Удаляет все настройки для личных чатов и очищает все связанные данные"""
    async with db_semaphore:
        success = False
        try:
            with safe_db_connect() as conn:
                cursor = conn.cursor()
                
                # Получаем список личных чатов (положительные ID)
                cursor.execute('''
                SELECT chat_id FROM chat_settings 
                WHERE CAST(chat_id AS INTEGER) > 0
                ''')
                
                personal_chats = [row[0] for row in cursor.fetchall()]
                
                if not personal_chats:
                    logger.info("Личных чатов не найдено")
                    return True
                    
                logger.info(f"Найдены личные чаты: {personal_chats}")
                
                # Для каждого личного чата удаляем данные
                for chat_id in personal_chats:
                    # Получаем ID опросов для этого чата
                    cursor.execute('''
                    SELECT id FROM polls WHERE chat_id = ?
                    ''', (chat_id,))
                    
                    poll_ids = [row[0] for row in cursor.fetchall()]
                    
                    # Удаляем записи о голосах для этих опросов
                    if poll_ids:
                        placeholders = ', '.join(['?'] * len(poll_ids))
                        cursor.execute(f'''
                        DELETE FROM votes WHERE poll_id IN ({placeholders})
                        ''', poll_ids)
                    
                    # Удаляем записи об опросах для этого чата
                    cursor.execute('''
                    DELETE FROM polls WHERE chat_id = ?
                    ''', (chat_id,))
                    
                    # Удаляем настройки чата
                    cursor.execute('''
                    DELETE FROM chat_settings WHERE chat_id = ?
                    ''', (chat_id,))
                    
                    # Удаляем записи о последней активности
                    cursor.execute('''
                    DELETE FROM last_activity WHERE chat_id = ?
                    ''', (chat_id,))
                    
                    logger.info(f"Удалены данные для личного чата {chat_id}")
                
                conn.commit()
                success = True
                logger.info("Личные чаты успешно удалены")
        except Exception as e:
            log_error_with_link("Database error in remove_personal_chat_settings", e)
            
        return success
