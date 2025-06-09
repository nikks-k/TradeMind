import pandas as pd, pandas_ta as ta, asyncio, numpy as np
from data_feed import TOP_PAIRS, binance

def _sentiment(val: float, thresh: float = 0.0):
    return ("bullish", 1)  if val >  thresh else \
           ("bearish", -1) if val < -thresh else ("neutral", 0)

async def tech_signals() -> list[dict]:
    loop, out = asyncio.get_event_loop(), []
    for pair in TOP_PAIRS:
        ohlcv = await loop.run_in_executor(None, binance.fetch_ohlcv,
                                           pair, "1m", None, 120)
        df = pd.DataFrame(ohlcv, columns="ts o h l c v".split())

    #     # ─ индикаторы ──────────────────────────────────────
    #     df["sma20"], df["sma50"] = ta.sma(df["c"], 20), ta.sma(df["c"], 50)
    #     df["ema12"], df["ema26"] = ta.ema(df["c"], 12), ta.ema(df["c"], 26)
    #     macd = ta.macd(df["c"])
    #     df["macd"]  = macd["MACD_12_26_9"]
    #     df["rsi14"] = ta.rsi(df["c"], 14)
    #     bb = ta.bbands(df["c"], 20)
    #     df["bb_pct"] = (df["c"] - bb["BBL_20_2.0"]) / (bb["BBU_20_2.0"] - bb["BBL_20_2.0"])

    #     # ─ переводим в «оценки» ────────────────────────────
    #     w = {"sma": .25, "ema": .25, "macd": .20, "rsi": .15, "bb": .15}
    #     last = df.iloc[-1]

    #     # 1) SMA-кросс
    #     sma_sig = np.sign(last.sma20 - last.sma50)
    #     # 2) EMA-кросс
    #     ema_sig = np.sign(last.ema12 - last.ema26)
    #     # 3) MACD
    #     macd_sig = np.sign(last.macd)
    #     # 4) RSI (70/30)
    #     rsi_sig = 1 if last.rsi14 > 70 else -1 if last.rsi14 < 30 else 0
    #     # 5) BB% (>0.8 перекуплен, <0.2 перепродан)
    #     bb_sig = 1 if last.bb_pct > 0.8 else -1 if last.bb_pct < 0.2 else 0

    #     score = (
    #         w["sma"]*sma_sig + w["ema"]*ema_sig + w["macd"]*macd_sig +
    #         w["rsi"]*rsi_sig + w["bb"]*bb_sig
    #     )
    #     sentiment, sign = _sentiment(score, 0.1)

    #     out.append({
    #         "asset":     pair.split("/")[0],
    #         "sentiment": sentiment,
    #         "conf":      abs(score),         # 0…1
    #         "score":     float(score),       # -1…1
    #         "reason":    f"sma:{sma_sig:+} ema:{ema_sig:+} macd:{macd_sig:+} "
    #                      f"rsi:{rsi_sig:+} bb:{bb_sig:+} → {score:+.2f}"
    #     })
    # return out

        df["sma8"], df["sma20"]    = ta.sma(df["c"], 8),  ta.sma(df["c"], 20)
        df["ema5"], df["ema13"]    = ta.ema(df["c"], 5),  ta.ema(df["c"], 13)
        macd = ta.macd(df["c"], fast=6, slow=13, signal=4)       # ускоренный MACD ←
        df["macd"]  = macd["MACD_6_13_4"]
        df["rsi7"]  = ta.rsi(df["c"], 7)
        bb = ta.bbands(df["c"], 20)
        df["bb_pct"] = (
            (df["c"] - bb["BBL_20_2.0"]) /
            (bb["BBU_20_2.0"] - bb["BBL_20_2.0"])
        )

        # --- Сигналы ----------------------------------------------------
        w = {"sma": .25, "ema": .25, "macd": .20, "rsi": .15, "bb": .15}
        last = df.iloc[-1]

        sma_sig  = np.sign(last.sma8 - last.sma20)          # кросс 8/20
        ema_sig  = np.sign(last.ema5 - last.ema13)          # кросс 5/13
        macd_sig = np.sign(last.macd)
        rsi_sig  = 1 if last.rsi7 > 70 else -1 if last.rsi7 < 30 else 0
        bb_sig   = 1 if last.bb_pct > 0.8 else -1 if last.bb_pct < 0.2 else 0

        score = (
            w["sma"]*sma_sig + w["ema"]*ema_sig + w["macd"]*macd_sig +
            w["rsi"]*rsi_sig + w["bb"]*bb_sig
        )
        sentiment, _ = _sentiment(score, 0.1)

        out.append({
            "asset":     pair.split("/")[0],
            "sentiment": sentiment,
            "conf":      abs(score),
            "score":     float(score),
            "reason": (
                f"sma:{sma_sig:+} ema:{ema_sig:+} macd:{macd_sig:+} "
                f"rsi:{rsi_sig:+} bb:{bb_sig:+} → {score:+.2f}"
            )
        })
    return out