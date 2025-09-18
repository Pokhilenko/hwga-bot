import asyncio
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

from dota_analytics.clients.opendota import OpenDotaClient
from dota_analytics.db.dota_models import Hero, Item, Match, MatchPlayer, ExtSteamLink, ExtChatMember
from dota_analytics.db.db_session import get_db
from dota_analytics.config import settings

class SyncService:
    def __init__(self, opendota_client: OpenDotaClient):
        self.opendota_client = opendota_client

    async def sync_reference_data(self):
        print("Syncing reference data (heroes and items)...")
        async with asyncio.TaskGroup() as tg:
            heroes_task = tg.create_task(self.opendota_client.get_heroes())
            items_task = tg.create_task(self.opendota_client.get_items())

        heroes_data = heroes_task.result()
        items_data = items_task.result()

        db: Session
        for db in get_db():
            # Sync Heroes
            for hero_id, hero_info in heroes_data.items():
                db_hero = db.query(Hero).filter(Hero.id == hero_id).first()
                if not db_hero:
                    db_hero = Hero(id=hero_id)
                    db.add(db_hero)
                db_hero.name_slug = hero_info.get("name")
                db_hero.localized_name = hero_info.get("localized_name")
                db_hero.primary_attr = hero_info.get("primary_attr")
                db_hero.roles = hero_info.get("roles")
            db.commit()

            # Sync Items
            for item_name_slug, item_info in items_data.items():
                # Skip items without a name or that are not actual items (e.g., recipes)
                if not item_info.get("id") or not item_info.get("localized_name"): # or item_info.get("recipe"):
                    continue

                db_item = db.query(Item).filter(Item.name_slug == item_name_slug).first()
                if not db_item:
                    db_item = Item(name_slug=item_name_slug)
                    db.add(db_item)
                db_item.localized_name = item_info.get("localized_name")
                db_item.cost = item_info.get("cost")
            db.commit()
        print("Reference data sync complete.")

    async def _fetch_and_store_player_matches(self, db: Session, steam32_id: int, since_days: int = None, latest_match_time: datetime = None):
        # Convert since_days to date filter for OpenDota API
        date_filter = None
        if since_days:
            date_filter = since_days

        # OpenDota API returns recent matches, so we can just fetch them
        # and filter by latest_match_time if provided
        matches_data = await self.opendota_client.get_player_recent_matches(account_id=steam32_id, date=date_filter)

        new_matches_count = 0
        for match_data in matches_data:
            match_id = match_data.get("match_id")
            start_time = datetime.fromtimestamp(match_data.get("start_time"))

            if latest_match_time and start_time <= latest_match_time:
                continue # Skip already processed matches

            db_match = db.query(Match).filter(Match.match_id == match_id).first()
            if not db_match:
                db_match = Match(
                    match_id=match_id,
                    start_time=start_time,
                    duration_sec=match_data.get("duration"),
                    radiant_win=match_data.get("radiant_win")
                )
                db.add(db_match)
                new_matches_count += 1

                # Add match player data
                db_match_player = MatchPlayer(
                    match_id=match_id,
                    steam32_id=steam32_id,
                    hero_id=match_data.get("hero_id"),
                    kills=match_data.get("kills"),
                    deaths=match_data.get("deaths"),
                    assists=match_data.get("assists"),
                    is_radiant=match_data.get("is_radiant"),
                    last_hits=match_data.get("last_hits"),
                    gpm=match_data.get("gold_per_min"),
                    xpm=match_data.get("xp_per_min"),
                    lane_role=match_data.get("lane_role")
                )
                db.add(db_match_player)
        return new_matches_count

    async def initial_player_import(self, steam32_ids: list[int]):
        print(f"Starting initial import for {len(steam32_ids)} players...")
        db: Session
        for db in get_db():
            for steam32_id in steam32_ids:
                print(f"Importing matches for player {steam32_id}...")
                new_matches = await self._fetch_and_store_player_matches(db, steam32_id, since_days=settings.SYNC_DEFAULT_DAYS)
                db.commit()
                print(f"Player {steam32_id}: Imported {new_matches} new matches.")
        print("Initial player import complete.")

    async def incremental_sync(self, steam32_ids: list[int]):
        print(f"Starting incremental sync for {len(steam32_ids)} players...")
        db: Session
        for db in get_db():
            for steam32_id in steam32_ids:
                latest_match = db.query(Match).join(MatchPlayer).filter(MatchPlayer.steam32_id == steam32_id).order_by(Match.start_time.desc()).first()
                latest_match_time = latest_match.start_time if latest_match else None

                print(f"Syncing matches for player {steam32_id} (latest match: {latest_match_time})...")
                new_matches = await self._fetch_and_store_player_matches(db, steam32_id, latest_match_time=latest_match_time)
                db.commit()
                print(f"Player {steam32_id}: Synced {new_matches} new matches.")
        print("Incremental sync complete.")

    async def etl_telegram_shadow_tables(self, telegram_db_adapter):
        print("Starting ETL for Telegram shadow tables...")
        db: Session
        for db in get_db():
            # Clear existing shadow tables
            db.query(ExtSteamLink).delete()
            db.query(ExtChatMember).delete()
            db.commit()

            # Fetch data from Telegram DB (using adapter)
            steam_links_data = await telegram_db_adapter.get_all_steam_links()
            chat_members_data = await telegram_db_adapter.get_all_chat_members()

            # Insert into shadow tables
            for sl in steam_links_data:
                db.add(ExtSteamLink(steam32_id=sl["steam32_id"], user_id=sl["user_id"]))
            for cm in chat_members_data:
                db.add(ExtChatMember(chat_id=cm["chat_id"], user_id=cm["user_id"], display_name=cm["display_name"]))
            db.commit()
        print("ETL for Telegram shadow tables complete.")

# Placeholder for Telegram DB adapter (to be implemented or provided by user)
class TelegramDBAdapter:
    async def get_all_steam_links(self):
        # This should query the existing Telegram DB
        # Example return format: [{'user_id': 123, 'steam32_id': 12345}]
        return []

    async def get_all_chat_members(self):
        # This should query the existing Telegram DB
        # Example return format: [{'chat_id': -1001, 'user_id': 123, 'display_name': 'User One'}]
        return []
