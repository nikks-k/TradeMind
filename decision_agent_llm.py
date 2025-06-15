"""
LLM-узел графа:
    • 2-кратная повторная попытка, если ответ пуст или не-JSON
    • робастный парсер (_safe_load_orders) – режет markdown, лишние \n
    • fallback-rule включается только после всех попыток
    • Key-synonyms нормализуются («size», «SIZE_PCT», action в любом регистре)
"""

import os, re, json, asyncio, logging, traceback, requests
from datetime import datetime
from typing import Dict, List

from wallet import wallet, DD_TRIGGER, DD_STOP, SIZE_PCT_LIMIT, COOLDOWN_MIN
from decision_agent import fuse_and_trade

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL    = "google/gemini-2.5-pro-preview"
BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_ATTEMPTS = 2                      # ← попробуем LLM два раза


# ───────────────────────── HTTP  ──────────────────────────────────────────
def _http_llm(messages: List[Dict]) -> str:
    pay = {"model": MODEL, "temperature": .15, "messages": messages}
    hdr = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type":  "application/json",
        "HTTP-Referer":  "http://localhost",
        "X-Title":       "crypto-multi-agent-mvp",
    }
    r = requests.post(BASE_URL, json=pay, headers=hdr, timeout=45)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

async def _call_llm(prompt: str) -> str:
    SYSTEM = (
        "Ты внутридневной крипто-трейдер. Верни *ТОЛЬКО* JSON-массив приказов\n"
        "[{\"asset\":\"BTC\",\"action\":\"BUY|SELL|HOLD\",\"size_pct\":0.03,"
        "\"reason\":\"…\"}, …]. size_pct ≤ 0.03; "
        "… Верни *СТРОГО* массив, и **каждый** объект обязан иметь "
        "\"reason\":\"…\" (минимум 3 слова).;"
        " SELL возможен *только* при "
        "открытой позиции; не трать >10 % equity на один актив."
    )
    msg = [{"role": "system", "content": SYSTEM},
           {"role": "user",   "content": prompt}]
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _http_llm, msg)


# ───────────────────────── robust JSON parse ──────────────────────────────
def _safe_load_orders(raw: str) -> list[dict]:
    """
    Извлекает первый JSON-массив из строки:
        • срезает ```json … ```   • удаляет лишние \n
        • возвращает [] если parse не удался
    """
    if not raw or not raw.strip():
        return []
    m = re.search(r"```json(.*?)```", raw, flags=re.S | re.I)
    if m:
        raw = m.group(1)
    m = re.search(r"\[.*\]", raw, flags=re.S)
    if not m:
        return []
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return []


# ─────────────────────── LangGraph-node ───────────────────────────────────
async def decide_llm(state: Dict) -> Dict:
    prices, tech, news = state["prices"], state["tech"], state["news"]

    txt  = ["Текущие цены:"] + [f"{a}:{p}" for a, p in prices.items()]
    txt += ["\nТех-сигналы:"] + [f"{t['asset']} {t['score']:+.2f}" for t in tech]
    txt += ["\nНовости:"]    + [f"{n['asset']} {n['sentiment']} {n['confidence']:.2f}" for n in news]
    prompt = "\n".join(txt)[:4000]

    orders: list[dict] = []
    reason_tag = "LLM decision"

    # ----------- 1-2 попытки LLM ------------------------------------------
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            raw = await _call_llm(prompt)
            logger.debug("RAW LLM RESPONSE (try %d):\n%s", attempt, raw)
            orders = _safe_load_orders(raw)
            if orders:
                break                                 # успех
            raise ValueError("empty/invalid JSON")
        except Exception as ex:
            logger.warning("LLM-error #%d → %s", attempt, ex)
            if attempt == MAX_ATTEMPTS:
                reason_tag = "fallback rule-based"
                orders = []
            else:
                await asyncio.sleep(1.0)             # краткая пауза и retry

    # ----------- если orders пустой → fallback ----------------------------
    reasons: list[str] = []
    if not orders:
        reasons = fuse_and_trade(news, tech, wallet, prices)
        return _out(state, reasons, tag=reason_tag)

    # ----------- нормализация и исполнение приказов -----------------------
    for o in orders:
        sym = (o.get("asset") or "").upper()
        act = (o.get("action") or "HOLD").upper()
        pct = o.get("size_pct") or o.get("size") or 0
        pct = min(float(pct), SIZE_PCT_LIMIT)
        rsn = o.get("reason", "")
        px  = prices.get(sym)

        if px is None or wallet.in_cooldown(sym):
            continue

        if act == "BUY" and pct > 0:
            wallet.buy(sym, px, pct=pct, prices=prices)
            reasons.append(f"{sym}: BUY {pct*100:.1f}% — {rsn}")
        elif act == "SELL":
            wallet.sell(sym, px)
            reasons.append(f"{sym}: SELL — {rsn}")
        else:
            reasons.append(f"{sym}: HOLD — {rsn}")

    # ----------- авто-exit + draw-down (без изменений) --------------------
    for sym in list(wallet.positions):
        if (px := prices.get(sym)) and wallet.should_exit(sym, px):
            wallet.sell(sym, px); reasons.append(f"{sym}: auto-exit")

    equity = wallet.total_equity(prices)
    drawdn = max(0, -wallet.unrealized_pnl(prices) / equity)
    if drawdn > DD_TRIGGER:
        losers = sorted(wallet.positions.items(),
                        key=lambda kv: (prices.get(kv[0], 0)-kv[1].entry_price)/kv[1].entry_price)
        for sym, _ in losers:
            if sym in prices:
                wallet.sell(sym, prices[sym], pct=0.5)
                reasons.append(f"{sym}: cut DD {drawdn:.2%}")
                equity = wallet.total_equity(prices)
                drawdn = max(0, -wallet.unrealized_pnl(prices) / equity)
                if drawdn <= DD_STOP:
                    break

    return _out(state, reasons, tag=reason_tag)


# ───────────────────────── helper ─────────────────────────────────────────
def _out(state, reasons, *, tag):
    return {
        "wallet": wallet,
        "equity": wallet.total_equity(state["prices"]),
        "events": [{
            "ts": datetime.utcnow().strftime("%H:%M:%S"),
            "msg": tag,
            "extra": {"reasons": reasons},
        }],
    }
