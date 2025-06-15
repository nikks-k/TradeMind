"""
Читает новости-сигналы из Postgres:
1) Если таблицы ещё не созданы, создаём их «на лету» и тихо
   возвращаем [] — граф продолжает работу.
2) Вся работа с БД остаётся синхронной через sync_engine
   (thread-pool executor), поэтому конфликтов event-loop нет.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import ProgrammingError, OperationalError

from database import sync_engine, Base            
from models    import NewsLLMCache

WINDOW_HOURS = 6  # берём новости «не старше» 6 ч


# ───────────────────────── helpers ────────────────────────────────────────
def _read_db(dt_from):
    """
    Blocking-SELECT в отдельном потоке.  Если таблицы ещё не существуют
    (первый запуск до rss_listener), создаём всю схему и возвращаем [].
    """
    try:
        with Session(sync_engine) as sess:
            return (
                sess.execute(
                    select(NewsLLMCache)
                    .where(NewsLLMCache.created_at >= dt_from)
                )
                .scalars()
                .all()
            )
    except (ProgrammingError, OperationalError):
        # Таблиц нет → создаём и продолжаем без падения
        Base.metadata.create_all(sync_engine)
        return []


# ───────────────────────── публичный API ─────────────────────────────────
async def _fetch_latest() -> list[dict]:
    dt_from = datetime.utcnow() - timedelta(hours=WINDOW_HOURS)
    loop = asyncio.get_running_loop()
    rows = await loop.run_in_executor(None, _read_db, dt_from)

    # оставляем запись с max(confidence) для каждого asset
    best: dict[str, NewsLLMCache] = {}
    for r in rows:
        if r.asset not in best or r.confidence > best[r.asset].confidence:
            best[r.asset] = r

    return [
        dict(
            asset=r.asset,
            sentiment=r.sentiment,
            confidence=r.confidence,
            reason=r.reason,
        )
        for r in best.values()
    ]


async def news_signals() -> list[dict]:
    """Асинхронный источник новостей для графа (thread-safe)."""
    return await _fetch_latest()
