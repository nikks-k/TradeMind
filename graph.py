from typing import Dict, List, TypedDict
from datetime import datetime

import networkx as nx, pydot                      # визуализация
from langgraph.graph import StateGraph, END

from wallet         import Wallet
from data_feed      import get_last_prices
from news_agent     import news_signals
from tech_agent     import tech_signals
from decision_agent import fuse_and_trade


# ─────────────────── состояние ───────────────────
class GState(TypedDict, total=False):
    prices:  Dict[str, float]
    tech:    List[Dict]
    news:    List[Dict]
    wallet:  "Wallet"
    equity:  float
    events:  List[Dict]          # будем заполнять в decide


wallet = Wallet()
_ev = lambda m, e=None: {"ts": datetime.utcnow().strftime("%H:%M:%S"),
                         "msg": m, "extra": e or {}}

# ─────────────────── узлы ─────────────────────────
async def get_prices(_: GState) -> GState:
    return {"prices": await get_last_prices()}

async def calc_tech(_: GState) -> GState:
    tech = await tech_signals()
    return {"tech": tech}

async def parse_news(_: GState) -> GState:
    return {"news": list(news_signals())}

async def decide(state: GState) -> GState:
    reasons = fuse_and_trade(state["news"], state["tech"],
                             wallet, state["prices"])

    events = [
        _ev("prices ✓",  state["prices"]),
        _ev("tech ✓",    state["tech"]),
        _ev("news ✓",    state["news"]),
        _ev("decision ✓", {"wallet": wallet.positions,
                           "reasons": reasons}),
    ]
    return {
        "wallet": wallet,
        "equity": wallet.total_equity(state["prices"]),
        "events": events,
    }

# ─────────────────── граф ─────────────────────────
g = StateGraph(state_schema=GState)
g.add_node("get_prices", get_prices)
g.add_node("calc_tech",  calc_tech)
g.add_node("parse_news", parse_news)
g.add_node("decide",     decide)

g.set_entry_point("get_prices")
g.add_edge("get_prices", "calc_tech")
g.add_edge("get_prices", "parse_news")
g.add_edge("calc_tech",  "decide")
g.add_edge("parse_news", "decide")
g.add_edge("decide",     END)

workflow = g.compile()           # ← экспортируем в app.py


# ─────────────────── viz helper ──────────────────
def display_graph_dot() -> str:
    """Возвращает dot-строку для st.graphviz_chart()."""
    G = nx.DiGraph()
    G.add_edges_from([
        ("get_prices", "calc_tech"),
        ("get_prices", "parse_news"),
        ("calc_tech",  "decide"),
        ("parse_news", "decide"),
    ])
    return pydot.graph_from_dot_data(nx.nx_pydot.to_pydot(G).to_string())[0].to_string()
