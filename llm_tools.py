import asyncio, json
from datetime import datetime, timedelta
from sqlalchemy import select
from database import AsyncSession
from models    import NewsLLMCache
from tech_agent import tech_signals           
from data_feed  import get_last_prices, ensure_pairs

# — news -------------------------------------------------------------------
async def _sql_latest_news(asset: str, n=5) -> list[dict]:
    dt_from = datetime.utcnow() - timedelta(hours=6)
    async with AsyncSession() as s:
        rows = (await s.execute(
            select(NewsLLMCache)
            .where(NewsLLMCache.asset==asset)
            .where(NewsLLMCache.created_at>=dt_from)
            .order_by(NewsLLMCache.confidence.desc())
            .limit(n)
        )).scalars().all()
    return [dict(asset=r.asset, sentiment=r.sentiment,
                 confidence=r.confidence, reason=r.reason) for r in rows]

# — tools для LangChain —
from langchain.tools import tool

@tool
async def get_news(asset: str) -> str:
    """Верни JSON-строку новостей по asset (BTC,ETH…)."""
    return json.dumps(await _sql_latest_news(asset))

@tool
async def get_tech(asset: str) -> str:
    """Верни JSON-строку текущего техсигнала по asset."""
    sigs = {t["asset"]:t for t in await tech_signals()}
    return json.dumps(sigs.get(asset, {}))

@tool
async def get_prices(asset: str) -> float:
    """Последняя цена asset."""
    return (await get_last_prices()).get(asset, 0.0)
