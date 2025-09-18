# Dota 2 Analytics Module for Telegram Bot

This module provides Dota 2 match analytics and LLM-generated summaries for your Telegram bot. It integrates with the OpenDota API to sync player match data into a dedicated PostgreSQL database and exposes REST endpoints for fetching aggregated statistics.

## Features

- **OpenDota Data Sync:** Synchronizes player match data, heroes, and items from OpenDota API.
- **Dedicated Database:** Stores all Dota 2 related data in a separate `dota_stats` PostgreSQL database.
- **Aggregated Statistics:** Provides endpoints to fetch summary statistics for a chat, including overall win rates, player-specific stats (games, wins, KDA), and duo performance.
- **LLM Summaries:** Generates sarcastic and witty summaries of match statistics using the Gemini API.
- **Shadow Tables:** Materializes Telegram DB data (steam links, chat members) into local shadow tables for efficient querying.

## Tech Stack

- **Language:** Python 3.11+
- **Framework:** FastAPI (API)
- **DB:** PostgreSQL 14+ (SQLAlchemy / Alembic for migrations)
- **HTTP Client:** `httpx` with `tenacity` for retries and custom rate limiting.
- **LLM:** Gemini API (`google-generativeai`)

## Environment Variables

Configure the module using the following environment variables:

- `DOTA_DB_DSN`: Connection string for the Dota analytics PostgreSQL database (e.g., `postgresql+psycopg2://user:pass@host:5432/dota_stats`)
- `TG_DB_DSN`: (Read-only) Connection string for the existing Telegram bot PostgreSQL database (e.g., `postgresql+psycopg2://user:pass@host:5432/telegram_db`)
- `OPENDOTA_API_KEY`: (Optional) Your OpenDota API key for higher rate limits. If not provided, public rate limits apply.
- `OPENDOTA_BASE`: Base URL for the OpenDota API (default: `https://api.opendota.com/api`)
- `SYNC_DEFAULT_DAYS`: Number of days to look back for initial player match import (default: `60`)
- `SYNC_CRON`: Cron expression for nightly incremental sync (default: `0 4 * * *`)
- `DEEP_MATCH_ENRICH`: (Boolean, default: `false`) Set to `true` to backfill detailed item and skill data for recent matches (heavy operation).
- `GEMINI_API_KEY`: Your Gemini API key for LLM summary generation.

## How to Run (Manual Steps - Docker/Testing Skipped)

Since Docker and testing steps are skipped, you will need to manually set up the environment and run the services.

1.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

2.  **Set Environment Variables:**
    Ensure all required environment variables (especially `DOTA_DB_DSN` and `GEMINI_API_KEY`) are set in your environment or in a `.env` file.

3.  **Run Database Migrations:**
    You will need to run Alembic migrations for the `dota_stats` database. Make sure your `DOTA_DB_DSN` points to a running PostgreSQL instance.
    ```bash
    alembic -c dota_analytics/db/migrations/alembic.ini upgrade head
    ```

4.  **Start the API Service:**
    ```bash
    uvicorn dota_analytics.api.main:app --host 0.0.0.0 --port 8000
    ```

## Initial Sync for a Chat

To perform an initial sync for players linked in a specific chat:

1.  **ETL Telegram Shadow Tables:** First, materialize the `ext_steam_links` and `ext_chat_members` tables from your Telegram DB.
    ```bash
    curl -X POST http://localhost:8000/admin/sync/etl_telegram_shadow_tables
    ```

2.  **Identify Steam32 IDs:** Get the `steam32_id`s of the users in the chat you want to sync. You would typically get this from your Telegram DB.

3.  **Initial Player Import:** Trigger the initial import for these `steam32_id`s.
    ```bash
    curl -X POST http://localhost:8000/admin/sync/initial_player_import \
         -H "Content-Type: application/json" \
         -d '[12345, 67890]' # Replace with actual steam32_ids
    ```

## Example API Calls

### Get Summary Statistics

```bash
curl -X GET "http://localhost:8000/stats/summary?chat_id=123456789&days=7"
```

**Sample Output:**

```json
{
  "period": {"from": "2025-09-11T...
  "overall": {"games": 10, "wins": 6, "winrate": 60.0},
  "players": [
    {"name": "User1", "steam32": 123, "games": 5, "wins": 3, "winrate": 60.0, "kda_avg": 2.5, "hero_top": ["Pudge", "Invoker"]}
  ],
  "duos": [
    {"pair": ["User1", "User2"], "games": 3, "wins": 2}
  ],
  "highlights": {"best": {}, "worst": {}}
}
```

### Generate LLM Summary

```bash
curl -X POST "http://localhost:8000/llm/summary" \
     -H "Content-Type: application/json" \
     -d '{
           "context": {
             "period": {"from": "2025-09-11T...", "to": "2025-09-18T..."},
             "overall": {"games": 10, "wins": 6, "winrate": 60.0},
             "players": [
               {"name": "User1", "steam32": 123, "games": 5, "wins": 3, "winrate": 60.0, "kda_avg": 2.5, "hero_top": ["Pudge", "Invoker"]},
               {"name": "User2", "steam32": 456, "games": 5, "wins": 3, "winrate": 60.0, "kda_avg": 2.0, "hero_top": ["Juggernaut", "Crystal Maiden"]}
             ],
             "duos": [
               {"pair": ["User1", "User2"], "games": 3, "wins": 2}
             ],
             "highlights": {"best": {}, "worst": {}}
           },
           "style": "roast",
           "max_lines": 6
         }'
```

**Sample LLM Output:**

```text
"Looks like a typical week in Dota. User1 and User2 managed to scrape by with a 60% winrate, which is... fine, I guess. User1's Pudge is still hooking air, but at least they're trying. User2's Juggernaut is carrying hard, as usual. Maybe try buying wards next time, fellas?"
```