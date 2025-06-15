import time, uuid, asyncio, logging
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from database import sync_engine         
from models    import Trade
from mcp_client import query             

logger = logging.getLogger(__name__)

# ───────── риск-параметры ────────────────────────────────────────────────
FEE_MAP        = {"BTC": 0.0011, "ETH": 0.0010}
SLIPPAGE       = 0.0007
SIZE_PCT_LIMIT = 0.03
MAX_POS_SHARE  = 0.10
MIN_TICKET     = 20

TP  = 0.015
SL  = 0.006
MAX_HOLD_MIN = 240
COOLDOWN_MIN = 15
DD_TRIGGER   = 0.005
DD_STOP      = 0.003


@dataclass
class Position:
    qty: float
    entry_price: float
    opened_ts: float


@dataclass
class Wallet:
    cash: float = 10_000.0
    positions: Dict[str, Position] = field(default_factory=dict)
    history:   List[Tuple[float, str]] = field(default_factory=list)
    realized:  float = 0.0
    last_op:   Dict[str, float] = field(default_factory=dict)

    # ---------- helpers ---------------------------------------------------
    def _fee_pct(self, sym): return FEE_MAP.get(sym, 0.001)
    def _log(self, msg):      self.history.append((time.time(), msg))

    def in_cooldown(self, sym: str) -> bool:
        ts = self.last_op.get(sym, 0)
        return (time.time() - ts) < COOLDOWN_MIN * 60

    def total_equity(self, prices: Dict[str, float]) -> float:
        return self.cash + sum(
            pos.qty * prices.get(sym, 0) for sym, pos in self.positions.items()
        )

    def unrealized_pnl(self, prices: Dict[str, float]) -> float:
        return sum(
            (prices.get(sym, 0) - pos.entry_price) * pos.qty
            for sym, pos in self.positions.items()
        )

    # ---------- postgres write (non-blocking) -----------------------------
    def _store(self, **kw):
        def _w():
            with Session(sync_engine) as s:
                s.add(Trade(**kw)); s.commit()
        asyncio.get_running_loop().run_in_executor(None, _w)

    # ---------- BUY -------------------------------------------------------
    def buy(self, sym: str, price: float, pct: float, *, prices):
        if self.in_cooldown(sym): return
        pct = min(pct, SIZE_PCT_LIMIT)
        fee_pct = self._fee_pct(sym)
        alloc   = max(self.cash * pct, MIN_TICKET)
        if alloc > self.cash or price <= 0: return
        qty = alloc / (price * (1 + fee_pct + SLIPPAGE))

        equity  = self.total_equity(prices)
        cur_val = self.positions.get(sym, Position(0, 0, 0)).qty * price
        if (cur_val + qty*price) > equity * MAX_POS_SHARE: return

        cost = qty * price * (1 + fee_pct + SLIPPAGE)
        self.cash -= cost

        if sym in self.positions:
            p = self.positions[sym]
            new_qty   = p.qty + qty
            new_price = (p.qty*p.entry_price + qty*price) / new_qty
            self.positions[sym] = Position(new_qty, new_price, p.opened_ts)
        else:
            self.positions[sym] = Position(qty, price, time.time())

        self.last_op[sym] = time.time()
        self._log(f"BUY  {sym} {qty:.4f} @ {price:.2f}")
        self._store(id=uuid.uuid4(), ts=datetime.utcnow(),
                    symbol=sym, side="BUY", qty=qty, price=price,
                    fee=cost - qty*price, realized_pnl=0.0)

    # ---------- SELL ------------------------------------------------------
    def sell(self, sym: str, price: float, pct: float = 1.0):
        if self.in_cooldown(sym): return
        pos = self.positions.get(sym);  fee_pct = self._fee_pct(sym)
        if not pos: return
        qty = pos.qty * pct
        proceeds = qty * price * (1 - fee_pct - SLIPPAGE)
        pnl      = proceeds - qty * pos.entry_price

        self.realized += pnl
        self.cash     += proceeds
        if pct >= 0.999: self.positions.pop(sym)
        else:            pos.qty -= qty

        self.last_op[sym] = time.time()
        self._log(f"SELL {sym} {qty:.4f} @ {price:.2f}  P&L {pnl:.2f}")
        self._store(id=uuid.uuid4(), ts=datetime.utcnow(),
                    symbol=sym, side="SELL", qty=qty, price=price,
                    fee=qty*price*fee_pct, realized_pnl=pnl)

    # ---------- TP / SL / timeout ----------------------------------------
    def should_exit(self, sym: str, price_now: float) -> bool:
        if self.in_cooldown(sym):
            return False
        pos = self.positions.get(sym)
        if not pos: return False
        delta = (price_now - pos.entry_price) / pos.entry_price
        if delta >= TP or delta <= -SL:
            return True
        return (time.time() - pos.opened_ts) >= MAX_HOLD_MIN * 60


# ───────── singleton wallet ───────────────────────────────────────────────
wallet = Wallet()

# ───────── подгружаем «последние операции» из trades ─────────────────────
try:
    rows = query(f"""
        SELECT symbol, ts
        FROM trades
        WHERE ts >= now() - interval '{COOLDOWN_MIN} minutes';
    """)
    for r in rows:
        ts = datetime.fromisoformat(str(r["ts"])).replace(tzinfo=timezone.utc).timestamp()
        wallet.last_op[r["symbol"]] = ts
    if rows:
        logger.info("Wallet cooldown restored for: %s",
                    ", ".join(wallet.last_op.keys()))
except Exception as ex:                    # не блокируем старт
    logger.warning("Could not restore cooldown from DB: %s", ex)
