from typing import List, Dict

# веса и порог
W_TECH, W_NEWS = 0.6, 0.4
THRESHOLD      = 0.45

def fuse_and_trade(news_sig: List[Dict],
                   tech_sig: List[Dict],
                   wallet,
                   prices: Dict[str, float]) -> List[str]:
    # агрегируем новости по каждому активу
    n_map = {}
    for n in news_sig:
        a   = n.get("asset", "general")
        if a == "general":
            continue
        sign = {"bullish": 1, "bearish": -1, "neutral": 0}[n["sentiment"]]
        n_map.setdefault(a, []).append(sign * n.get("confidence", 0.5))

    reasons = []
    for t in tech_sig:
        a = t["asset"]
        s_tech = t["score"]                  # уже –1 … +1
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
