import ccxt, asyncio, heapq

binance = ccxt.binance({'enableRateLimit': True})

# ────────────────────────── фильтры ──────────────────────────
STABLES_BASE = {
    "USDC", "FDUSD", "BUSD", "TUSD", "USDP",
    "DAI", "UST", "USTC", "USD", "EUR", "GBP"
}
VOL_MIN = 50_000_000       # ≥ 50 M USDT/24 h
MAX_PAIRS = 8              # верхний лимит

# ───────────────────────── выбор топ-пар ─────────────────────
async def get_top_pairs(limit: int = MAX_PAIRS,
                        quote: str = "USDT") -> list[str]:
    tickers = binance.fetch_tickers()
    pairs: list[tuple[float, str]] = []
    for symbol, t in tickers.items():
        if not symbol.endswith(f"/{quote}"):
            continue
        base, _ = symbol.split("/")            # BTC/USDT → BTC
        if base in STABLES_BASE:               # убираем стейблкоины
            continue
        if t["quoteVolume"] < VOL_MIN:         # убираем малообъёмные
            continue
        pairs.append((t["quoteVolume"], symbol))
    top = heapq.nlargest(limit, pairs)         # сортировка по объёму
    return [s for _, s in top]

# получаем список один раз при старте; обновлять можно CRON-ом
TOP_PAIRS = asyncio.run(get_top_pairs())

# ───────────────────────── текущие цены ──────────────────────
async def get_last_prices() -> dict[str, float]:
    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(None, binance.fetch_ticker, p)
             for p in TOP_PAIRS]
    tickers = await asyncio.gather(*tasks)
    return {p.split("/")[0]: t["last"]
            for p, t in zip(TOP_PAIRS, tickers)}
