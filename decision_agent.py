from typing import List, Dict

# веса и порог
W_TECH, W_NEWS = 0.6, 0.4
THRESHOLD      = 0.55          

# карта тональностей
_SENT_MAP = {
    "bullish": 1, "positive": 1,  "up": 1,
    "bearish": -1, "negative": -1, "down": -1,
    "neutral": 0,  "flat": 0
}

def fuse_and_trade(news_sig: List[Dict],
                   tech_sig: List[Dict],
                   wallet,
                   prices: Dict[str, float]) -> List[str]:

    # агрегируем новости по активу
    n_map: Dict[str, List[float]] = {}
    for n in news_sig:
        a = n.get("asset", "general")
        if a == "general":
            continue
        # используем .get() с дефолтом 0
        sign = _SENT_MAP.get(n.get("sentiment", "").lower(), 0)
        n_map.setdefault(a, []).append(sign * n.get("confidence", 0.5))

    # ---- авто-закрытие открытых позиций ----------------------------------
    reasons: List[str] = []

    for sym in list(wallet.positions):
        price_now = prices.get(sym)
        if price_now is not None and wallet.should_exit(sym, price_now):
            wallet.sell(sym, price_now)
            reasons.append(f"{sym}: auto-exit TP/SL/timeout")

    # ---- финальный score --------------------------------------------------
    for t in tech_sig:
        a = t["asset"]
        s_tech = t["score"]                  # –1 … +1
        if a not in prices:                  # биржа не вернула цену
            continue

        if a in n_map:
            s_news = sum(n_map[a]) / len(n_map[a])
            w_news, w_tech = W_NEWS, W_TECH
        else:
            s_news = 0.0                     # нет новости → чистая техника
            w_news, w_tech = 0.0, 1.0

        score = w_tech * s_tech + w_news * s_news

        if score >= THRESHOLD:
            wallet.buy(a, prices[a], pct=0.05, prices=prices)
            reasons.append(f"{a}: score {score:+.2f} → BUY")
        elif score <= -THRESHOLD:
            wallet.sell(a, prices[a])
            reasons.append(f"{a}: score {score:+.2f} → SELL")
        else:
            reasons.append(f"{a}: score {score:+.2f} → HOLD")
    return reasons
