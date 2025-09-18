from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from dota_analytics.db.dota_models import Match, MatchPlayer, ExtSteamLink, ExtChatMember
from dota_analytics.db.db_session import get_db

class PartyService:
    def __init__(self):
        pass

    def get_party_matches_for_chat(self, chat_id: int, since_time: datetime = None):
        db: Session
        for db in get_db():
            # This query needs to be optimized, potentially using the materialized view
            # For now, a direct query to demonstrate the logic
            chat_steam32_ids = [s.steam32_id for s in db.query(ExtSteamLink.steam32_id)
                                .join(ExtChatMember, ExtChatMember.user_id == ExtSteamLink.user_id)
                                .filter(ExtChatMember.chat_id == chat_id).all()]

            if not chat_steam32_ids:
                return []

            # Find matches where at least two players from the chat participated
            party_matches_query = db.query(Match.match_id)
            .join(MatchPlayer, Match.match_id == MatchPlayer.match_id)
            .filter(MatchPlayer.steam32_id.in_(chat_steam32_ids))
            .group_by(Match.match_id)
            .having(func.count(MatchPlayer.steam32_id) >= 2)

            if since_time:
                party_matches_query = party_matches_query.filter(Match.start_time >= since_time)

            return [m.match_id for m in party_matches_query.all()]
