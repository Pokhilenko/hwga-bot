from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from dota_analytics.db.dota_models import Match, MatchPlayer, ExtSteamLink, ExtChatMember, Hero
from dota_analytics.db.db_session import get_db

class StatsService:
    def __init__(self):
        pass

    def _calculate_winrate(self, wins: int, games: int) -> float:
        return (wins / games * 100) if games > 0 else 0.0

    def _get_chat_steam32_ids(self, db: Session, chat_id: int) -> list[int]:
        return [s.steam32_id for s in db.query(ExtSteamLink.steam32_id)
                .join(ExtChatMember, ExtChatMember.user_id == ExtSteamLink.user_id)
                .filter(ExtChatMember.chat_id == chat_id).all()]

    def get_summary_stats(self, chat_id: int, days: int = None, since_time: datetime = None):
        db: Session
        for db in get_db():
            period_start = None
            if days:
                period_start = datetime.now() - timedelta(days=days)
            elif since_time:
                period_start = since_time

            chat_steam32_ids = self._get_chat_steam32_ids(db, chat_id)

            # Overall stats for the chat
            overall_games_query = db.query(func.count(Match.match_id))
            if period_start:
                overall_games_query = overall_games_query.filter(Match.start_time >= period_start)
            overall_games = overall_games_query.scalar()

            overall_wins_query = db.query(func.count(Match.match_id))
            if period_start:
                overall_wins_query = overall_wins_query.filter(Match.start_time >= period_start)
            overall_wins = overall_wins_query.filter(Match.radiant_win == True).scalar()

            overall_winrate = self._calculate_winrate(overall_wins, overall_games)

            # Player stats
            player_stats_query = db.query(
                ExtSteamLink.user_id,
                ExtChatMember.display_name,
                func.count(MatchPlayer.match_id).label("games"),
                func.sum(func.case(
                    (and_(Match.radiant_win == True, MatchPlayer.is_radiant == True), 1),
                    (and_(Match.radiant_win == False, MatchPlayer.is_radiant == False), 1),
                    else_=0
                )).label("wins"),
                func.avg((MatchPlayer.kills.cast(float) + MatchPlayer.assists) / func.nullif(MatchPlayer.deaths, 0)).label("kda_avg"),
                func.array_agg(Hero.localized_name).label("hero_top") # This needs to be refined for top heroes
            ).join(Match, Match.match_id == MatchPlayer.match_id)
            .join(ExtSteamLink, ExtSteamLink.steam32_id == MatchPlayer.steam32_id)
            .join(ExtChatMember, and_(ExtChatMember.user_id == ExtSteamLink.user_id, ExtChatMember.chat_id == chat_id))
            .outerjoin(Hero, Hero.id == MatchPlayer.hero_id)
            .filter(MatchPlayer.steam32_id.in_(chat_steam32_ids))

            if period_start:
                player_stats_query = player_stats_query.filter(Match.start_time >= period_start)

            player_stats_query = player_stats_query.group_by(ExtSteamLink.user_id, ExtChatMember.display_name)
            player_stats_raw = player_stats_query.all()

            players_data = []
            for p_stat in player_stats_raw:
                players_data.append({
                    "name": p_stat.display_name,
                    "steam32": p_stat.user_id, # This is actually Telegram user_id, not steam32_id
                    "games": p_stat.games,
                    "wins": p_stat.wins,
                    "winrate": self._calculate_winrate(p_stat.wins, p_stat.games),
                    "kda_avg": round(p_stat.kda_avg, 2) if p_stat.kda_avg else 0.0,
                    "hero_top": p_stat.hero_top # Needs aggregation logic
                })

            # Duos stats (simplified for now, needs proper party detection)
            duos_data = [] # This will be complex and likely require a materialized view or more advanced queries

            return {
                "period": {"from": period_start.isoformat() if period_start else None, "to": datetime.now().isoformat()},
                "overall": {"games": overall_games, "wins": overall_wins, "winrate": overall_winrate},
                "players": players_data,
                "duos": duos_data,
                "highlights": {"best": {}, "worst": {}} # To be implemented
            }

    def get_stats_for_party(self, chat_id: int, steam32_ids: list[int], days: int = None):
        # This will be similar to get_summary_stats but filtered by specific steam32_ids
        # and will need to implement the party detection logic.
        pass
