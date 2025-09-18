from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from typing import Optional

from dota_analytics.services.stats import StatsService
from dota_analytics.llm.summary import LLMSummaryService

router = APIRouter()

@router.get("/summary")
async def get_summary(chat_id: int, days: Optional[int] = None, stats_service: StatsService = Depends(StatsService)):
    if not days:
        raise HTTPException(status_code=400, detail="'days' parameter is required for summary stats.")
    stats = stats_service.get_summary_stats(chat_id=chat_id, days=days)
    return stats

@router.get("/since_last_poll")
async def get_summary_since_last_poll(chat_id: int, stats_service: StatsService = Depends(StatsService)):
    # Placeholder: In a real scenario, this would query the Telegram DB for the last poll end time.
    # For now, let's assume a fixed time or get it from a mock adapter.
    last_poll_end_time = datetime.now() - timedelta(days=7) # Example: last 7 days
    stats = stats_service.get_summary_stats(chat_id=chat_id, since_time=last_poll_end_time)
    return stats

@router.get("/party")
async def get_party_stats(chat_id: int, users: str, days: Optional[int] = None, stats_service: StatsService = Depends(StatsService)):
    steam32_ids = [int(s_id) for s_id in users.split(",")]
    stats = stats_service.get_stats_for_party(chat_id=chat_id, steam32_ids=steam32_ids, days=days)
    return stats

@router.post("/llm/summary")
async def generate_llm_summary(context: dict, style: str = "neutral", max_lines: int = 6, llm_service: LLMSummaryService = Depends(LLMSummaryService)):
    summary_text = await llm_service.generate_summary(context, style, max_lines)
    return {"text": summary_text}
