from sqlalchemy import Column, Integer, String, BigInteger, Boolean, SmallInteger, ARRAY, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import TEXT, TIMESTAMP

Base = declarative_base()

class Hero(Base):
    __tablename__ = 'heroes'
    id = Column(Integer, primary_key=True)
    name_slug = Column(String, nullable=False, unique=True)
    localized_name = Column(String, nullable=False)
    primary_attr = Column(String)
    roles = Column(ARRAY(String))

class Item(Base):
    __tablename__ = 'items'
    name_slug = Column(String, primary_key=True)
    localized_name = Column(String)
    cost = Column(Integer)

class Match(Base):
    __tablename__ = 'matches'
    match_id = Column(BigInteger, primary_key=True)
    start_time = Column(TIMESTAMP(timezone=True), nullable=False)
    duration_sec = Column(Integer)
    radiant_win = Column(Boolean)

    players = relationship("MatchPlayer", back_populates="match")

class MatchPlayer(Base):
    __tablename__ = 'match_players'
    match_id = Column(BigInteger, ForeignKey('matches.match_id', ondelete='CASCADE'), primary_key=True)
    steam32_id = Column(Integer, primary_key=True)
    hero_id = Column(Integer, ForeignKey('heroes.id'))
    kills = Column(SmallInteger)
    deaths = Column(SmallInteger)
    assists = Column(SmallInteger)
    is_radiant = Column(Boolean)
    last_hits = Column(Integer)
    gpm = Column(Integer)
    xpm = Column(Integer)
    lane_role = Column(SmallInteger)

    match = relationship("Match", back_populates="players")
    hero = relationship("Hero")

class PlayerItem(Base):
    __tablename__ = 'player_items'
    match_id = Column(BigInteger, primary_key=True)
    steam32_id = Column(Integer, primary_key=True)
    slot = Column(SmallInteger, primary_key=True)
    item_slug = Column(String, ForeignKey('items.name_slug'))

    item = relationship("Item")

class PlayerSkill(Base):
    __tablename__ = 'player_skills'
    match_id = Column(BigInteger, primary_key=True)
    steam32_id = Column(Integer, primary_key=True)
    order_idx = Column(SmallInteger, primary_key=True)
    ability_id = Column(Integer)
    time_seconds = Column(Integer)

# Shadow tables for Telegram DB data
class ExtSteamLink(Base):
    __tablename__ = 'ext_steam_links'
    steam32_id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False) # Telegram user ID

class ExtChatMember(Base):
    __tablename__ = 'ext_chat_members'
    chat_id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, primary_key=True) # Telegram user ID
    display_name = Column(String) # User's display name in the chat
