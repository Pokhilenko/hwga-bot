import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    DOTA_DB_DSN: str = os.getenv("DOTA_DB_DSN", "postgresql+psycopg2://user:pass@localhost:5433/dota_stats")
    TG_DB_DSN: str = os.getenv("TG_DB_DSN", "postgresql+psycopg2://user:pass@localhost:5434/telegram_db")
    OPENDOTA_API_KEY: str | None = os.getenv("OPENDOTA_API_KEY")
    OPENDOTA_BASE: str = os.getenv("OPENDOTA_BASE", "https://api.opendota.com/api")
    SYNC_DEFAULT_DAYS: int = int(os.getenv("SYNC_DEFAULT_DAYS", "60"))
    SYNC_CRON: str = os.getenv("SYNC_CRON", "0 4 * * *")
    DEEP_MATCH_ENRICH: bool = os.getenv("DEEP_MATCH_ENRICH", "false").lower() == "true"
    GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")

settings = Settings()
