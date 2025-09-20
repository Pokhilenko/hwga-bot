import asyncio
import logging
from datetime import datetime, timedelta

import aiohttp

import db
from exceptions import DatabaseError, DotaApiError
import summary
from utils import convert_steamid_64_to_32

# Import new analytics services
from dota_analytics.clients.opendota import OpenDotaClient
from dota_analytics.services.sync import SyncService, TelegramDBAdapter

logger = logging.getLogger(__name__)

# Initialize OpenDotaClient and SyncService globally or pass them around
# For simplicity in this example, we'll initialize them here. In a larger app,
# you might use dependency injection.
opendota_client = OpenDotaClient()
sync_service = SyncService(opendota_client)
telegram_db_adapter = TelegramDBAdapter() # Placeholder, needs actual implementation

async def _send_opendota_request(endpoint):
    """Helper function to send a request to the OpenDota API."""
    url = f"https://api.opendota.com/api/{endpoint}"
    logger.info(f"Sending OpenDota API request to {url}")

    matches = None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise DotaApiError(f"OpenDota API returned status {response.status}")
                matches = await response.json()
                logger.info(f"OpenDota API request to {url} response is {matches}")
                return matches
    except aiohttp.ClientError as e:
        raise DotaApiError(f"Error in OpenDota API request: {e}")


async def verify_steam_id(steam_id_64):
    """Verify Steam ID by checking if it exists in OpenDota API."""
    steam_id_32 = convert_steamid_64_to_32(steam_id_64)
    try:
        data = await _send_opendota_request(f"players/{steam_id_32}")
        if not data or "profile" not in data:
            return None

        profile_data = {
            "steam_id": data["profile"]["steamid"],
            "username": data["profile"]["personaname"],
            "profile_url": data["profile"]["profileurl"],
            "avatar": data["profile"]["avatar"],
        }
        return profile_data
    except DotaApiError as e:
        logger.error(f"Error verifying Steam ID {steam_id_32}: {e}")
        return None


async def get_player_dota_stats(steam_id_32, limit=100):
    """Get player's Dota 2 stats from OpenDota API."""
    try:
        # This function is now deprecated in favor of using SyncService directly
        # However, keeping it for backward compatibility if other parts of the bot still use it.
        data = await _send_opendota_request(f"players/{steam_id_32}/matches?limit={limit}")
        return data
    except DotaApiError as e:
        logger.error(f"Error getting player dota stats for {steam_id_32}: {e}")
        return None


async def get_match_details(match_id):
    """Get details of a Dota 2 match from OpenDota API."""
    try:
        data = await _send_opendota_request(f"matches/{match_id}")
        return data
    except DotaApiError as e:
        logger.error(f"Error getting match details for {match_id}: {e}")
        return None


async def get_steam_player_statuses(chat_id: str):
    """Get the Steam status of all users in a chat."""
    try:
        user_steam_ids_32 = await db.get_chat_steam_ids_32(chat_id)
        if not user_steam_ids_32:
            return "⚠️ В этом чате нет пользователей с привязанными Steam ID.\n\nИспользуйте команду /link_steam для привязки аккаунта."

        online_players = []
        offline_players = []

        for steam_id_32 in user_steam_ids_32:
            try:
                data = await _send_opendota_request(f"players/{steam_id_32}")
                if data and data.get("profile"):
                    if data.get("profile").get("last_login") is None:
                        offline_players.append(data["profile"]["personaname"])
                    else:
                        last_login_time = datetime.fromisoformat(data["profile"]["last_login"].replace("Z", "+00:00"))
                        if datetime.now(last_login_time.tzinfo) - last_login_time < timedelta(minutes=30):
                            online_players.append(data["profile"]["personaname"])
                        else:
                            offline_players.append(data["profile"]["personaname"])
                else:
                    logger.warning(f"No OpenDota user data for {steam_id_32}")
                    user_info = await db.get_user_info_by_steam_id_32(steam_id_32)
                    if user_info:
                        offline_players.append(user_info["first_name"])
                    else:
                        offline_players.append(f"Unknown user ({steam_id_32})")

            except DotaApiError as e:
                logger.error(f"Error getting OpenDota data for {steam_id_32}: {e}")
                user_info = await db.get_user_info_by_steam_id_32(steam_id_32)
                if user_info:
                    offline_players.append(user_info["first_name"])
                else:
                    offline_players.append(f"Unknown user ({steam_id_32})")

        lines = []
        if online_players:
            lines.append("Онлайн:")
            lines.append(", ".join(online_players))
        if offline_players:
            lines.append("Оффлайн:")
            lines.append(", ".join(offline_players))

        return "\n".join(lines)

    except (DatabaseError, DotaApiError) as e:
        logger.error(f"Error getting user statuses: {e}")
        return f"❌ Произошла непредвиденная ошибка: {str(e)}"


async def check_and_store_dota_games(context):
    """Check for and store Dota 2 games based on poll participants."""
    logger.info("Checking for Dota 2 games from polls...")
    participants = await db.get_game_participants()
    if not participants:
        logger.info("No game participants from recent polls found.")
        return

    logger.info(f"Found {len(participants)} game participants from polls.")

    chat_participants = {}
    for p in participants:
        if p.chat_id not in chat_participants:
            chat_participants[p.chat_id] = []
        chat_participants[p.chat_id].append(p)

    for chat_id, participant_group in chat_participants.items():
        if len(participant_group) < 2:
            continue

        user_ids = [p.user_id for p in participant_group]
        steam_ids_32 = [convert_steamid_64_to_32(user.steam_id) for user in (await asyncio.gather(*[db.get_user_info(uid) for uid in user_ids])) if user and user.get("steam_id")]

        if len(steam_ids_32) < 2:
            continue

        # Use the new sync service for storing matches
        await sync_service.incremental_sync(steam_ids_32) # Assuming incremental sync is appropriate here

        participant_ids_to_delete = [p.id for p in participant_group]
        await db.delete_game_participants(participant_ids_to_delete)
        logger.info(f"Deleted {len(participant_ids_to_delete)} game participants for chat {chat_id}.")


async def check_games_on_demand(context, chat_id, days):
    """Check for games on demand for all linked users in a chat."""
    logger.info(f"Checking for games on demand in chat {chat_id} for the last {days} days.")

    # First, ETL Telegram shadow tables to ensure up-to-date user data
    await sync_service.etl_telegram_shadow_tables(telegram_db_adapter)

    user_steam_ids_32 = await db.get_chat_steam_ids_32(chat_id)
    
    if not user_steam_ids_32:
        await context.bot.send_message(chat_id=chat_id, text="No users with linked Steam accounts in this chat.")
        return

    # Use the new sync service for initial import (or incremental if preferred)
    await sync_service.initial_player_import(user_steam_ids_32) # This will fetch matches for 'days' back

    await context.bot.send_message(chat_id=chat_id, text=f"Initiated game data sync for {len(user_steam_ids_32)} users in the last {days} days. Statistics will be available shortly.")


# The following functions are no longer needed as match storage is handled by SyncService
# async def _find_and_store_single_player_games(context, chat_id, steam_id_32, days):
#     pass

# async def _find_and_store_common_games(context, chat_id, steam_ids_32, days):
#     pass