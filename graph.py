from typing import Dict, List, TypedDict
from datetime import datetime

import networkx as nx, pydot
from langgraph.graph import StateGraph, END

from wallet import Wallet, wallet  

from data_feed      import get_last_prices
from news_agent     import news_signals
from tech_agent     import tech_signals
from decision_agent_llm import decide_llm

# ─────────────── схема состояния ─────────────────────────────────────────
class GState(TypedDict, total=False):
    prices:  Dict[str, float]
    tech:    List[Dict]
    news:    List[Dict]
    wallet:  Wallet            
    equity:  float
    events:  List[Dict]

_ev = lambda m, e=None: {"ts": datetime.utcnow().strftime("%H:%M:%S"),
                         "msg": m, "extra": e or {}}

# ─────────────── узлы графа ───────────────────────────────────────────────
async def get_prices(_: GState) -> GState:
    return {"prices": await get_last_prices()}

async def calc_tech(_: GState) -> GState:
    return {"tech": await tech_signals()}

async def parse_news(_: GState) -> GState:
    return {"news": await news_signals()}

# ─────────────── сборка графа LangGraph ──────────────────────────────────
g = StateGraph(state_schema=GState)

g.add_node("get_prices", get_prices)
g.add_node("calc_tech",  calc_tech)
g.add_node("parse_news", parse_news)
g.add_node("decide_llm", decide_llm)

g.set_entry_point("get_prices")
g.add_edge("get_prices", "calc_tech")
g.add_edge("get_prices", "parse_news")
g.add_edge("calc_tech",  "decide_llm")
g.add_edge("parse_news", "decide_llm")
g.add_edge("decide_llm", END)

workflow = g.compile()        # ← экспортируется в app.py

# ─────────────── helper для Streamlit-визуализации ───────────────────────
def display_graph_dot() -> str:
    G = nx.DiGraph()
    G.add_edges_from([
        ("get_prices", "calc_tech"),
        ("get_prices", "parse_news"),
        ("calc_tech",  "decide_llm"),
        ("parse_news", "decide_llm"),
    ])
    return pydot.graph_from_dot_data(
        nx.nx_pydot.to_pydot(G).to_string()
    )[0].to_string()
