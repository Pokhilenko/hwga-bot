import asyncio
import logging
from datetime import datetime, timedelta

import aiohttp

import db
from poll_state import poll_state
from exceptions import SteamApiError

# Configure logging
logger = logging.getLogger(__name__)


async def _send_steam_request(steam_id, steam_api_key, action_description):
    """Helper function to send a request to the Steam API with retry logic."""
    if not steam_api_key:
        raise SteamApiError(f"Steam API key not set, cannot {action_description}")

    url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={steam_api_key}&steamids={steam_id}"
    logger.info(f"Sending Steam API request for {steam_id} to {action_description}")

    max_retries = 3
    for retry in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 429:  # Too Many Requests
                        logger.warning(
                            f"Steam API rate limit (429) hit when trying to {action_description} for Steam ID {steam_id}, retry {retry + 1}/{max_retries}"
                        )
                        if retry < max_retries - 1:
                            wait_time = (retry + 1) * 5
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            raise SteamApiError(
                                f"Max retries reached for Steam API request when trying to {action_description} for Steam ID {steam_id}"
                            )

                    if response.status != 200:
                        raise SteamApiError(
                            f"Steam API returned status {response.status} when trying to {action_description}"
                        )

                    return await response.json()

        except aiohttp.ClientError as e:
            logger.error(
                f"Error in Steam API request when trying to {action_description} for Steam ID {steam_id}: {e}"
            )
            if retry < max_retries - 1:
                wait_time = (retry + 1) * 5
                await asyncio.sleep(wait_time)
            else:
                raise SteamApiError(
                    f"Error in Steam API request when trying to {action_description} for Steam ID {steam_id}: {e}"
                )
    return None


async def verify_steam_id(steam_id, steam_api_key):
    """Verify Steam ID by checking if it exists in Steam API."""
    try:
        data = await _send_steam_request(steam_id, steam_api_key, "verify Steam ID")

        if not data:
            return None

        players = data.get("response", {}).get("players", [])
        if not players:
            logger.warning(f"No player found with Steam ID: {steam_id}")
            return None

        player_info = players[0]
        profile_data = {
            "steam_id": player_info.get("steamid"),
            "username": player_info.get("personaname", "Unknown"),
            "profile_url": player_info.get("profileurl", ""),
            "avatar": player_info.get("avatar", ""),
            "status": player_info.get("personastate", 0),
            "real_name": player_info.get("realname", ""),
            "visibility": player_info.get("communityvisibilitystate", 1),
        }

        logger.info(
            f"Successfully verified Steam ID: {steam_id}, username: {profile_data['username']}"
        )
        return profile_data
    except SteamApiError as e:
        logger.error(f"Error verifying Steam ID {steam_id}: {e}")
        return None


async def check_verification_code(steam_id, verification_code, steam_api_key):
    """
    Checks for the presence of a verification code in the Steam username.
    Returns True if the code is found, otherwise False.
    """
    try:
        data = await _send_steam_request(
            steam_id, steam_api_key, "check verification code"
        )

        if not data:
            return False

        players = data.get("response", {}).get("players", [])
        if not players:
            logger.warning(f"No player found with Steam ID: {steam_id}")
            return False

        player_info = players[0]
        username = player_info.get("personaname", "")

        if verification_code in username:
            logger.info(
                f"Verification code '{verification_code}' found in username '{username}'"
            )
            return True
        else:
            logger.info(
                f"Verification code '{verification_code}' NOT found in username '{username}'"
            )
            return False
    except SteamApiError as e:
        logger.error(f"Error checking verification code for Steam ID {steam_id}: {e}")
        return False


async def check_steam_status(context, steam_api_key, send_poll_func):
    """Check if users are playing Dota 2 and notify the chat."""
    if not steam_api_key:
        logger.warning("Steam API key not set, skipping Steam status check")
        return

    logger.info("Starting Steam status check...")

    try:
        # Get Steam users from database
        steam_users, last_activities = await db.get_steam_users()

        logger.info(f"Found {len(steam_users)} users with Steam IDs")

        # Debug: Print all users with Steam IDs
        for telegram_id, steam_id, first_name, chat_id in steam_users:
            logger.info(f"User: {first_name}, Steam ID: {steam_id}, Chat ID: {chat_id}")

        logger.info(f"Last activities: {last_activities}")

        # Group by chat_id
        chat_users = {}
        for telegram_id, steam_id, first_name, chat_id in steam_users:
            if not chat_id:  # Skip if no chat_id
                logger.warning(
                    f"Skipping user {first_name} because no chat_id is associated"
                )
                continue

            # Check if the Steam ID is specifically linked to this chat
            is_linked = await db.is_steam_id_linked_to_chat(telegram_id, chat_id)
            if not is_linked:
                logger.warning(
                    f"Skipping user {first_name} because Steam ID not linked to chat {chat_id}"
                )
                continue

            if chat_id not in chat_users:
                chat_users[chat_id] = []

            last_poll_end = None
            if chat_id in last_activities:
                last_poll_end = (
                    last_activities[chat_id]
                    if last_activities[chat_id]
                    else None
                )
                logger.info(f"Last poll end for chat {chat_id}: {last_poll_end}")

            chat_users[chat_id].append(
                {
                    "telegram_id": telegram_id,
                    "steam_id": steam_id,
                    "first_name": first_name,
                    "last_poll_end": last_poll_end,
                }
            )

        logger.info(f"Checking {len(chat_users)} chats for players")

        # Check each chat
        for chat_id, users in chat_users.items():
            # Skip if there's already an active poll
            if poll_state.is_active(chat_id):
                logger.info(f"Skipping chat {chat_id} because there's an active poll")
                continue

            logger.info(f"Checking {len(users)} users in chat {chat_id}")

            # Get users who might be playing Dota 2
            dota_players = []

            for user in users:
                # Skip if last poll end was less than 2 hours ago
                if user["last_poll_end"] and datetime.now() - user[
                    "last_poll_end"
                ] < timedelta(hours=2):
                    logger.info(
                        f"Skipping user {user['first_name']} because last poll was less than 2 hours ago"
                    )
                    continue

                # Check Steam status
                steam_id = user["steam_id"]
                logger.info(
                    f"Checking Steam status for {user['first_name']} (Steam ID: {steam_id})"
                )

                try:
                    await asyncio.sleep(2)
                    data = await _send_steam_request(
                        steam_id, steam_api_key, f"check status for {user['first_name']}"
                    )

                    if not data:
                        continue

                    players = data.get("response", {}).get("players", [])
                    if players:
                        player = players[0]
                        logger.info(
                            f"Player {user['first_name']} status: {player.get('gameextrainfo', 'Not in game')} (Game ID: {player.get('gameid', 'None')})"
                        )

                        # Check if playing Dota 2 (game ID 570)
                        if player.get("gameid"):
                            game_name = player.get(
                                "gameextrainfo", "Unknown game"
                            )
                            logger.info(
                                f"User {user['first_name']} is playing {game_name}!"
                            )
                            dota_players.append(
                                (user["first_name"], game_name)
                            )
                    else:
                        logger.warning(
                            f"No player data found for Steam ID: {steam_id}"
                        )

                except SteamApiError as e:
                    logger.error(
                        f"Error checking Steam status for {user['first_name']}: {e}"
                    )

            # If at least one person is playing Dota 2, send notification
            if dota_players:
                logger.info(f"Found players in chat {chat_id}: {dota_players}")

                # Group players by game
                games = {}
                for player, game in dota_players:
                    if game not in games:
                        games[game] = []
                    games[game].append(player)

                for game, players in games.items():
                    if len(players) == 1:
                        message = f"{players[0]} уже вовсю начал сасать в {game}, присоединяйтесь!"
                    else:
                        players_list = ", ".join(players[:-1]) + " и " + players[-1]
                        message = f"{players_list} уже вовсю начали сасать в {game}, присоединяйтесь!"

                    await context.bot.send_message(chat_id=chat_id, text=message)
            else:
                logger.info(f"No Dota 2 players found in chat {chat_id}")

        logger.info("Steam status check completed")

    except db.DatabaseError as e:
        logger.error(f"Database error in Steam status checker: {e}")
    except Exception as e:
        logger.error(f"Error in Steam status checker: {e}")
        import traceback

        logger.error(traceback.format_exc())


async def get_steam_player_statuses(chat_id: str, steam_api_key: str):
    """Get the Steam status of all users in a chat."""
    try:
        user_steam_ids = {}
        async with db.db_semaphore:
            with db.get_db_session() as session:
                steam_users = (
                    session.query(db.UserSteamChat.telegram_id, db.UserSteamChat.steam_id, db.User.first_name)
                    .join(db.User, db.User.telegram_id == db.UserSteamChat.telegram_id)
                    .filter(db.UserSteamChat.chat_id == chat_id)
                    .filter(db.UserSteamChat.steam_id.isnot(None))
                    .all()
                )

        logger.info(
            f"Found {len(steam_users)} users with linked Steam IDs in chat {chat_id}"
        )

        if not steam_users:
            return "⚠️ В этом чате нет пользователей с привязанными Steam ID.\n\nИспользуйте команду /link_steam для привязки аккаунта."

        for user_id, steam_id, first_name in steam_users:
            user_steam_ids[user_id] = {
                "steam_id": steam_id,
                "first_name": first_name,
            }

        dota_players = []
        online_users = []
        offline_users = []
        other_game_players = []

        for i, (user_id, user_data) in enumerate(user_steam_ids.items()):
            steam_id = user_data["steam_id"]
            first_name = user_data["first_name"]

            if i > 0:
                await asyncio.sleep(2)

            try:
                data = await _send_steam_request(
                    steam_id, steam_api_key, f"get status for {first_name}"
                )

                if not data:
                    offline_users.append(first_name)
                    continue

                players = data.get("response", {}).get("players", [])

                if not players:
                    logger.warning(f"No Steam user data for {steam_id}")
                    offline_users.append(first_name)
                    continue

                player = players[0]

                persona_state = player.get("personastate", 0)
                game_id = player.get("gameid", None)
                game_name = player.get("gameextrainfo", None)

                if game_id == "570":
                    dota_players.append(first_name)
                elif game_id:
                    game_display_name = game_name or "Unknown game"
                    other_game_players.append((first_name, game_display_name))
                elif persona_state > 0:
                    online_users.append(first_name)
                else:
                    offline_users.append(first_name)

            except SteamApiError as e:
                logger.error(
                    f"Error getting Steam data for {first_name} ({steam_id}): {e}"
                )
                offline_users.append(first_name)

        if len(offline_users) == len(user_steam_ids) and user_steam_ids:
            return "Сейчас все оффлайн"
        elif len(dota_players) == len(user_steam_ids) and user_steam_ids:
            return "Сейчас все играют в Dota 2"
        else:
            lines = []

            if dota_players:
                lines.append("В Dota 2:")
                lines.append(", ".join(dota_players))

            if other_game_players:
                lines.append("В другой игре:")

                game_groups = {}
                for name, game in other_game_players:
                    game_groups.setdefault(game, []).append(name)

                for game, players in game_groups.items():
                    players_str = ", ".join(players)
                    lines.append(f"{players_str}: {game}")

            if online_users:
                lines.append("Онлайн:")
                lines.append(", ".join(online_users))

            if offline_users and len(offline_users) != len(user_steam_ids):
                lines.append("Оффлайн:")
                lines.append(", ".join(offline_users))

            lines.append(f"Проверено пользователей: {len(user_steam_ids)}")

            if lines:
                return "\n".join(lines)
            else:
                return "Сейчас никто не играет"

    except db.DatabaseError as e:
        logger.error(f"Database error getting user statuses: {e}")
        return f"❌ Ошибка при получении данных из базы: {str(e)}"
    except Exception as e:
        logger.error(f"Error getting user statuses: {e}")
        return f"❌ Произошла непредвиденная ошибка: {str(e)}"