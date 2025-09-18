from fastapi import APIRouter, Depends, HTTPException
from typing import Optional

from dota_analytics.services.sync import SyncService, TelegramDBAdapter
from dota_analytics.clients.opendota import OpenDotaClient

router = APIRouter()

@router.post("/sync/reference_data")
async def sync_reference_data(sync_service: SyncService = Depends(lambda: SyncService(OpenDotaClient()))):
    await sync_service.sync_reference_data()
    return {"message": "Reference data sync initiated."}

@router.post("/sync/initial_player_import")
async def initial_player_import(steam32_ids: list[int], sync_service: SyncService = Depends(lambda: SyncService(OpenDotaClient()))):
    if not steam32_ids:
        raise HTTPException(status_code=400, detail="'steam32_ids' cannot be empty.")
    await sync_service.initial_player_import(steam32_ids)
    return {"message": f"Initial player import initiated for {len(steam32_ids)} players."}

@router.post("/sync/incremental")
async def incremental_sync(steam32_ids: list[int], sync_service: SyncService = Depends(lambda: SyncService(OpenDotaClient()))):
    if not steam32_ids:
        raise HTTPException(status_code=400, detail="'steam32_ids' cannot be empty.")
    await sync_service.incremental_sync(steam32_ids)
    return {"message": f"Incremental sync initiated for {len(steam32_ids)} players."}

@router.post("/sync/etl_telegram_shadow_tables")
async def etl_telegram_shadow_tables(sync_service: SyncService = Depends(lambda: SyncService(OpenDotaClient()))):
    # In a real scenario, you would pass a concrete TelegramDBAdapter instance here
    # For now, using the placeholder.
    await sync_service.etl_telegram_shadow_tables(TelegramDBAdapter())
    return {"message": "ETL for Telegram shadow tables initiated."}
