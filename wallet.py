import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

FEE = 0.001                 # 0 ,1 % комиссия Binance
MAX_POS_SHARE = 0.20        # ≤ 20 % equity на один актив

@dataclass
class Position:
    qty: float
    entry_price: float

@dataclass
class Wallet:
    cash: float = 10_000.0
    positions: Dict[str, Position] = field(default_factory=dict)
    history:   List[Tuple[float, str]] = field(default_factory=list)
    realized:  float = 0.0

    # ───────────── helpers ─────────────
    def _log(self, msg: str):
        self.history.append((time.time(), msg))

    def total_equity(self, prices: Dict[str, float]) -> float:
        eq = self.cash
        for s, p in self.positions.items():
            eq += p.qty * prices.get(s, 0.0)
        return eq

    # ───────────── BUY ────────────────
    def buy(self, symbol: str, price: float, pct: float = 0.05,
            prices: Dict[str, float] | None = None):
        if price <= 0 or self.cash < 1:
            return
        alloc = self.cash * pct
        qty   = alloc / (price * (1 + FEE))

        # лимит 20 % equity
        if prices:
            equity = self.total_equity(prices)
            cur_val = self.positions.get(symbol,
                                         Position(0, 0)).qty * price
            if (cur_val + qty * price) > equity * MAX_POS_SHARE:
                return

        self.cash -= qty * price * (1 + FEE)

        if symbol in self.positions:           # усреднение
            pos = self.positions[symbol]
            new_qty   = pos.qty + qty
            new_price = (pos.qty * pos.entry_price + qty * price) / new_qty
            self.positions[symbol] = Position(new_qty, new_price)
        else:
            self.positions[symbol] = Position(qty, price)

        self._log(f"BUY  {symbol} {qty:.4f} @ {price:.2f}")

    # ───────────── SELL ───────────────
    def sell(self, symbol: str, price: float, pct: float = 1.0):
        pos = self.positions.get(symbol)
        if not pos:
            return
        qty = pos.qty * pct
        proceeds = qty * price * (1 - FEE)
        self.realized += proceeds - qty * pos.entry_price
        self.cash += proceeds
        if pct >= 0.999:
            self.positions.pop(symbol)
        else:
            pos.qty -= qty
        self._log(f"SELL {symbol} {qty:.4f} @ {price:.2f} "
                  f"P&L={self.realized:.2f}")

    def unrealized_pnl(self, prices: dict[str, float]) -> float:
        return sum((prices.get(sym, 0)*p.qty - p.qty*p.entry_price)
                   for sym, p in self.positions.items())
    