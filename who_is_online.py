#!/usr/bin/env python3

import asyncio
import logging
import aiohttp
import sqlite3
import os
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Constants
DB_FILE = "poll_bot.db"
STEAM_API_KEY = os.environ.get("STEAM_API_KEY", "")


async def get_steam_users():
    """Retrieves Steam users from the database"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # Get users with linked Steam ID
        cursor.execute("""
        SELECT u.telegram_id, usc.steam_id, u.first_name, usc.chat_id 
        FROM user_steam_chats usc
        JOIN users u ON usc.telegram_id = u.telegram_id
        WHERE usc.steam_id IS NOT NULL
        GROUP BY u.telegram_id, usc.chat_id
        """)

        result = cursor.fetchall()
        conn.close()

        return result
    except Exception as e:
        logger.error(f"Ошибка при получении пользователей Steam: {e}")
        return []


async def check_steam_status(steam_id, steam_api_key):
    """Checks the status of a user on Steam"""
    if not steam_api_key:
        logger.warning("Steam API key не указан, невозможно проверить статус")
        return None

    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={steam_api_key}&steamids={steam_id}"

            # Retry mechanism to handle error 429
            max_retries = 3
            for retry in range(max_retries):
                try:
                    async with session.get(url) as response:
                        if response.status == 429:  # Too Many Requests
                            logger.warning(
                                f"Ошибка API Steam 429 для пользователя со Steam ID {steam_id}, попытка {retry + 1}/{max_retries}"
                            )
                            if retry < max_retries - 1:
                                wait_time = (retry + 1) * 5
                                await asyncio.sleep(wait_time)
                                continue
                            else:
                                logger.error(
                                    f"Достигнуто максимальное число попыток для Steam ID {steam_id}"
                                )
                                return None

                        if response.status != 200:
                            logger.error(
                                f"API Steam вернул статус {response.status} для Steam ID {steam_id}"
                            )
                            return None

                        data = await response.json()
                        players = data.get("response", {}).get("players", [])
                        if players:
                            player = players[0]
                            persona_state = player.get("personastate", 0)
                            game_id = player.get("gameid")
                            game_name = player.get("gameextrainfo")

                            logger.info(
                                f"Статус Steam для Steam ID {steam_id}: персона={persona_state}, игра={game_name} ({game_id})"
                            )

                            return {
                                "persona_state": persona_state,
                                "game_id": game_id,
                                "game_name": game_name,
                                "username": player.get("personaname", "Unknown"),
                            }
                        else:
                            logger.warning(
                                f"Не найдены данные игрока для Steam ID: {steam_id}"
                            )
                            return None

                        # Successfully received data, exiting the loop
                        break
                except Exception as e:
                    logger.error(
                        f"Ошибка запроса API Steam для Steam ID {steam_id}: {e}"
                    )
                    if retry < max_retries - 1:
                        wait_time = (retry + 1) * 5
                        await asyncio.sleep(wait_time)
                    else:
                        return None
    except Exception as e:
        logger.error(f"Ошибка проверки статуса Steam для Steam ID {steam_id}: {e}")
        return None


async def main():
    """Main function for checking the online status of Steam users"""
    if not STEAM_API_KEY:
        logger.error(
            "STEAM_API_KEY не установлен. Установите переменную окружения STEAM_API_KEY."
        )
        return

    # Get Steam users from the database
    steam_users = await get_steam_users()
    logger.info(f"Найдено {len(steam_users)} пользователей с привязкой Steam ID")

    # Dictionary for grouping users by chat
    users_by_chat = {}
    for telegram_id, steam_id, first_name, chat_id in steam_users:
        if chat_id not in users_by_chat:
            users_by_chat[chat_id] = []

        users_by_chat[chat_id].append(
            {"telegram_id": telegram_id, "steam_id": steam_id, "first_name": first_name}
        )

    # Check the status of each user in each chat
    for chat_id, users in users_by_chat.items():
        logger.info(f"Проверка {len(users)} пользователей в чате {chat_id}")

        online_users = []
        in_game_users = []

        for user in users:
            # Add a small delay between requests
            await asyncio.sleep(1)

            user_status = await check_steam_status(user["steam_id"], STEAM_API_KEY)

            if user_status:
                # Check persona status (0 = offline, 1+ = online)
                if user_status["persona_state"] > 0:
                    online_users.append(user["first_name"])
                    logger.info(f"Пользователь {user['first_name']} онлайн")

                    # Check if the user is playing a game
                    if user_status["game_id"]:
                        in_game_users.append(
                            {
                                "name": user["first_name"],
                                "game": user_status["game_name"]
                                or f"Игра ID {user_status['game_id']}",
                            }
                        )
                        logger.info(
                            f"Пользователь {user['first_name']} играет в {user_status['game_name'] or user_status['game_id']}"
                        )
                else:
                    logger.info(f"Пользователь {user['first_name']} офлайн")

        log_chat_results(chat_id, users, online_users, in_game_users)


def log_chat_results(chat_id, users, online_users, in_game_users):
    """Log aggregated results for a chat."""
    logger.info("=== Чат %s ===", chat_id)
    logger.info("Всего пользователей: %d", len(users))

    if online_users:
        logger.info(
            "Пользователи онлайн (%d): %s",
            len(online_users),
            ", ".join(online_users),
        )
    else:
        logger.info("Нет пользователей онлайн")

    if in_game_users:
        logger.info("Пользователи в игре (%d):", len(in_game_users))
        for user in in_game_users:
            logger.info("  - %s: %s", user["name"], user["game"])
    else:
        logger.info("Нет пользователей в игре")


if __name__ == "__main__":
    asyncio.run(main())
