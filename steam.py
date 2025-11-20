import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Set

import db
from exceptions import DatabaseError, DotaApiError
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
telegram_db_adapter = TelegramDBAdapter()


def _normalize_steam32_ids(raw_ids: Iterable[str]) -> List[int]:
    normalized = []
    for steam_id in raw_ids:
        try:
            normalized.append(int(steam_id))
        except (TypeError, ValueError):
            continue
    return normalized


async def _get_player_profile(steam32_id: int):
    try:
        return await opendota_client.get_player(account_id=steam32_id)
    except Exception as exc:  # pragma: no cover - networking
        raise DotaApiError(f"OpenDota player request failed: {exc}") from exc


async def _get_recent_matches(steam32_id: int, days: Optional[int] = None):
    try:
        return await opendota_client.get_player_recent_matches(
            account_id=steam32_id, date=days
        )
    except Exception as exc:  # pragma: no cover - networking
        raise DotaApiError(f"OpenDota recent matches failed: {exc}") from exc


async def _get_match_details_from_api(match_id: int):
    try:
        return await opendota_client.get_match(match_id)
    except Exception as exc:  # pragma: no cover - networking
        raise DotaApiError(f"OpenDota match request failed: {exc}") from exc


async def verify_steam_id(steam_id_64):
    """Verify Steam ID by checking if it exists in OpenDota API."""
    steam_id_32 = int(convert_steamid_64_to_32(steam_id_64))
    try:
        data = await _get_player_profile(steam_id_32)
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
        data = await opendota_client.get_player_recent_matches(
            account_id=int(steam_id_32), limit=limit
        )
        return data
    except Exception as e:  # pragma: no cover
        logger.error(f"Error getting player dota stats for {steam_id_32}: {e}")
        return None


async def get_match_details(match_id):
    """Get details of a Dota 2 match from OpenDota API."""
    try:
        data = await _get_match_details_from_api(int(match_id))
        return data
    except DotaApiError as e:  # pragma: no cover - logging
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

        for steam_id_32 in _normalize_steam32_ids(user_steam_ids_32):
            try:
                data = await _get_player_profile(steam_id_32)
                if data and data.get("profile"):
                    last_login = data["profile"].get("last_login")
                    if last_login is None:
                        offline_players.append(data["profile"]["personaname"])
                    else:
                        last_login_time = datetime.fromisoformat(
                            last_login.replace("Z", "+00:00")
                        )
                        if (
                            datetime.now(last_login_time.tzinfo) - last_login_time
                            < timedelta(minutes=30)
                        ):
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
        user_infos = await asyncio.gather(*[db.get_user_info(uid) for uid in user_ids])
        steam_ids_32_str = [
            convert_steamid_64_to_32(user["steam_id"])
            for user in user_infos
            if user and user.get("steam_id")
        ]

        normalized_ids = _normalize_steam32_ids(steam_ids_32_str)
        if len(normalized_ids) < 2:
            continue

        earliest_poll_end = min(
            (p.poll_end_time for p in participant_group if p.poll_end_time), default=None
        )
        since_epoch = None
        if earliest_poll_end:
            # Look for matches that started within ~2 hours around the poll end time
            since_epoch = int(
                (earliest_poll_end - timedelta(hours=2)).timestamp()
            )

        stored_matches = await _sync_chat_matches(
            chat_id, normalized_ids, since_epoch=since_epoch
        )
        logger.info(
            f"Stored {stored_matches} common matches for chat {chat_id} after poll."
        )

        # Keep the analytics database in sync as well
        await sync_service.incremental_sync(normalized_ids)

        participant_ids_to_delete = [p.id for p in participant_group]
        await db.delete_game_participants(participant_ids_to_delete)
        logger.info(f"Deleted {len(participant_ids_to_delete)} game participants for chat {chat_id}.")


async def check_games_on_demand(context, chat_id, days):
    """Check for games on demand for all linked users in a chat."""
    logger.info(f"Checking for games on demand in chat {chat_id} for the last {days} days.")

    raw_ids = await db.get_chat_steam_ids_32(chat_id)
    normalized_ids = _normalize_steam32_ids(raw_ids)
    
    if len(normalized_ids) < 2:
        await context.bot.send_message(chat_id=chat_id, text="No users with linked Steam accounts in this chat.")
        return

    stored_matches = await _sync_chat_matches(chat_id, normalized_ids, days=days)
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "Game scan complete. "
            f"Found {stored_matches} new match(es) for the last {days} day(s). "
            "Use /games_stat to view updated statistics."
        ),
    )

    # Refresh analytics storage so extended dashboards stay current
    await sync_service.etl_telegram_shadow_tables(telegram_db_adapter)
    await sync_service.initial_player_import(normalized_ids, since_days=days)


async def _sync_chat_matches(
    chat_id: str,
    steam32_ids: Sequence[int],
    *,
    days: Optional[int] = None,
    since_epoch: Optional[int] = None,
) -> int:
    """Fetch, deduplicate and store matches played by at least two chat members."""
    match_candidates = await _collect_common_match_ids(
        steam32_ids, days=days, since_epoch=since_epoch
    )

    stored = 0
    for match_id in match_candidates:
        if await db.get_match(match_id):
            continue
        details = await _get_match_details_from_api(match_id)
        if not details:
            continue
        await _store_match_from_details(chat_id, details)
        stored += 1
    return stored


async def _collect_common_match_ids(
    steam32_ids: Sequence[int],
    *,
    days: Optional[int],
    since_epoch: Optional[int],
) -> Set[int]:
    """Return match ids where multiple chat members played together."""
    match_participants: Dict[int, Set[int]] = defaultdict(set)
    player_tasks = {
        steam_id: asyncio.create_task(_get_recent_matches(steam_id, days))
        for steam_id in steam32_ids
    }

    for steam_id, task in player_tasks.items():
        try:
            matches = await task
        except DotaApiError as exc:
            logger.error(f"Failed to fetch matches for {steam_id}: {exc}")
            continue

        for match in matches or []:
            match_id = match.get("match_id")
            start_time = match.get("start_time")
            if match_id is None:
                continue
            if since_epoch and start_time and start_time < since_epoch:
                continue
            match_participants[match_id].add(steam_id)

    return {
        match_id
        for match_id, players in match_participants.items()
        if len(players) >= 2
    }


async def _store_match_from_details(chat_id: str, match_details: dict):
    """Persist a match to the local SQLite database."""
    match_id = match_details.get("match_id")
    if not match_id:
        return

    players = match_details.get("players", [])
    radiant_players = []
    dire_players = []

    for player in players:
        account_id = player.get("account_id")
        if account_id is None:
            continue
        if player.get("player_slot", 0) < 128:
            radiant_players.append(str(account_id))
        else:
            dire_players.append(str(account_id))

    winner = "radiant" if match_details.get("radiant_win") else "dire"

    await db.store_match(
        str(match_id),
        chat_id,
        winner,
        ",".join(radiant_players),
        ",".join(dire_players),
    )
