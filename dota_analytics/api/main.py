from fastapi import FastAPI
from dota_analytics.api.routes import stats, admin

app = FastAPI(
    title="Dota 2 Analytics API",
    description="API for Dota 2 statistics and LLM summaries.",
    version="0.1.0",
)

app.include_router(stats.router, prefix="/stats", tags=["Stats"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}