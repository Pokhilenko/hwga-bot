import httpx
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from datetime import datetime, timedelta
from collections import deque

from dota_analytics.config import settings

class RateLimiter:
    def __init__(self, rate_limit: int, period: int = 60):
        self.rate_limit = rate_limit
        self.period = period
        self.timestamps = deque()
        self.lock = asyncio.Lock()

    async def __aenter__(self):
        async with self.lock:
            while self.timestamps and self.timestamps[0] < datetime.now() - timedelta(seconds=self.period):
                self.timestamps.popleft()
            if len(self.timestamps) >= self.rate_limit:
                sleep_time = (self.timestamps[0] + timedelta(seconds=self.period) - datetime.now()).total_seconds()
                await asyncio.sleep(sleep_time)
            self.timestamps.append(datetime.now())

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

class OpenDotaClient:
    def __init__(self):
        self.base_url = settings.OPENDOTA_BASE
        self.api_key = settings.OPENDOTA_API_KEY
        self.client = httpx.AsyncClient(base_url=self.base_url)
        self.rate_limiter = RateLimiter(rate_limit=60) # Default 60 requests per minute

    async def _request(self, method: str, path: str, params: dict = None):
        headers = {}
        if self.api_key:
            # OpenDota typically uses query param for API key
            if params is None:
                params = {}
            params["api_key"] = self.api_key

        @retry(
            stop=stop_after_attempt(5),
            wait=wait_exponential(multiplier=1, min=4, max=10),
            retry=retry_if_exception_type(httpx.HTTPStatusError)
        )
        async def _send_request():
            async with self.rate_limiter:
                response = await self.client.request(method, path, params=params, headers=headers)
                response.raise_for_status()
                return response.json()
        return await _send_request()

    async def get_player_recent_matches(self, account_id: int, limit: int = None, date: int = None):
        params = {"limit": limit, "date": date} if limit or date else None
        return await self._request("GET", f"/players/{account_id}/recentMatches", params=params)

    async def get_player_wl(self, account_id: int):
        return await self._request("GET", f"/players/{account_id}/wl")

    async def get_match(self, match_id: int):
        return await self._request("GET", f"/matches/{match_id}")

    async def get_heroes(self):
        return await self._request("GET", "/constants/heroes")

    async def get_items(self):
        return await self._request("GET", "/constants/items")

    async def get_hero_stats(self):
        return await self._request("GET", "/heroStats")
