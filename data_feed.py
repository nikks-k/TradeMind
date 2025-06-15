"""
Клиент CCXT теперь делает 1 запрос exchangeInfo в самом начале и бросает
пары, которых нет на Binance -> больше нет лавины ошибок в логе.
"""
import asyncio, heapq, logging, time
import ccxt.async_support as ccxt

logger = logging.getLogger(__name__)

STABLES   = {"USDC","FDUSD","BUSD","TUSD","USDP","DAI","UST","USTC"}
VOL_MIN   = 50_000_000
MAX_PAIRS = 8
TTL_PAIRS = 3600

# ---------- helpers -------------------------------------------------------
def _make_client():
    """Создает и возвращает асинхронный клиент CCXT Binance."""
    return ccxt.binance({
        "enableRateLimit": True,
        "timeout": 15000, # Увеличим таймаут на всякий случай
        # Если нужны API ключи, их можно передать здесь из переменных окружения
        # 'apiKey': os.getenv('BINANCE_API_KEY'),
        # 'secret': os.getenv('BINANCE_SECRET_KEY'),
    })

async def _load_markets():
    # Используем _make_client для создания клиента
    async with _make_client() as c:
        return await c.load_markets()

_markets_cache: tuple[dict, float] | None = None

async def _markets():
    global _markets_cache
    now = time.time()
    if not _markets_cache or now - _markets_cache[1] > 900:
        _markets_cache = (await _load_markets(), now)
    return _markets_cache[0]

# ---------- TOP PAIRS -----------------------------------------------------
_pairs_cache: tuple[list[str], float] | None = None

async def _calc_pairs() -> list[str]:
    mkts = await _markets()
    # Используем _make_client для создания клиента
    async with _make_client() as c:
        tickers = await c.fetch_tickers()
    pool=[]
    for sym,t in tickers.items():
        if not sym.endswith("/USDT") or sym not in mkts: continue
        base,_ = sym.split("/")
        if base in STABLES or (t.get("quoteVolume") or 0) < VOL_MIN: continue
        pool.append((t["quoteVolume"], sym))
    top=[s for _,s in heapq.nlargest(MAX_PAIRS,pool)]
    logger.info("TOP_PAIRS refreshed → %s", top)
    return top

async def ensure_pairs()->list[str]:
    global _pairs_cache
    now=time.time()
    if not _pairs_cache or now-_pairs_cache[1]>TTL_PAIRS:
        _pairs_cache=(await _calc_pairs(),now)
    return _pairs_cache[0]

# ---------- PRICES --------------------------------------------------------
async def _safe_price(pair):
    try:
        # Используем _make_client для создания клиента
        async with _make_client() as c:
            t=await c.fetch_ticker(pair)
            return pair.split("/")[0], t["last"] or 0.0
    except Exception as e:
        logger.debug("ticker %s err: %s", pair, e)
        return pair.split("/")[0], None

async def get_last_prices()->dict[str,float]:
    pairs=await ensure_pairs()
    res=await asyncio.gather(*[asyncio.create_task(_safe_price(p)) for p in pairs])
    return {b:p for b,p in res if p is not None}