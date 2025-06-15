import asyncio, logging, numpy as np, pandas as pd, pandas_ta as ta
from datetime import datetime, timezone

from data_feed import ensure_pairs, _make_client          

logger   = logging.getLogger(__name__)
TF       = "5m"
CANDLES  = 120
RSI_OB, RSI_OS = 70, 30

def _sent(val: float, thr: float = 0.0):
    if val >  thr: return "bullish",  1
    if val < -thr: return "bearish", -1
    return "neutral", 0

def _indicators(df: pd.DataFrame) -> tuple[float,str]:
    close, last = df["close"], df.iloc[-1]
    sma = np.sign(ta.sma(close, 36).iloc[-1] - ta.sma(close, 80).iloc[-1])
    ema = np.sign(ta.ema(close, 16).iloc[-1] - ta.ema(close, 42).iloc[-1])
    mac = np.sign(ta.macd(close, 24, 52, 18)["MACD_24_52_18"].iloc[-1])
    rsi28 = ta.rsi(close, 28).iloc[-1]
    rsi = 1 if rsi28 > RSI_OB else -1 if rsi28 < RSI_OS else 0
    bb    = ta.bbands(close, 20)
    bbp   = (last.close - bb["BBL_20_2.0"].iloc[-1]) /\
            (bb["BBU_20_2.0"].iloc[-1] - bb["BBL_20_2.0"].iloc[-1])
    bbp = 1 if bbp > .8 else -1 if bbp < .2 else 0

    w = {"sma":.25,"ema":.25,"mac":.20,"rsi":.15,"bb":.15}
    score = w["sma"]*sma + w["ema"]*ema + w["mac"]*mac + w["rsi"]*rsi + w["bb"]*bbp
    reason = f"sma:{sma:+} ema:{ema:+} mac:{mac:+} rsi:{rsi:+} bb:{bbp:+}"
    return float(score), reason

async def _fetch(pair: str) -> dict | None:
    base = pair.split("/")[0]
    client = _make_client()
    try:
        ohlcv = await client.fetch_ohlcv(pair, timeframe=TF, limit=CANDLES)
    except Exception as e:
        logger.warning("ohlcv %s err: %s", pair, e)
        return None
    finally:
        await client.close()

    if not ohlcv:
        return None
    df = pd.DataFrame(ohlcv, columns="ts open high low close vol".split())
    score, reason = _indicators(df)
    sentiment, _  = _sent(score, 0.1)
    return {
        "asset": base,
        "sentiment": sentiment,
        "confidence": abs(score),
        "score": round(score,4),
        "reason": f"{reason} → {score:+.2f}",
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

async def tech_signals() -> list[dict]:
    pairs  = await ensure_pairs()
    tasks  = [asyncio.create_task(_fetch(p)) for p in pairs]
    res    = await asyncio.gather(*tasks)
    return [r for r in res if r]
