"""
Мини-клиент MCP Alchemy (HTTP → FastAPI)
"""
from __future__ import annotations
import os, requests, typing as _t
from functools import lru_cache

# ─── источники адреса ─────────────────────────────────────────────────────
_ENV_VAR      = os.getenv("MCP_SERVER_URL")          # приоритет №1
_CANDIDATES   = (
    "http://mcp:3333",
    "http://localhost:8081",
    "http://localhost:3333",
)

# ─── ping helper ──────────────────────────────────────────────────────────
def _is_alive(base: str) -> bool:
    try:
        r = requests.options(base.rstrip("/") + "/mcp", timeout=2)
        return r.status_code < 500          
    except requests.RequestException:
        return False

@lru_cache
def _discover_url() -> str:
    if _ENV_VAR and _is_alive(_ENV_VAR):
        return _ENV_VAR.rstrip("/")
    for url in _CANDIDATES:
        if _is_alive(url):
            return url.rstrip("/")
    raise RuntimeError(
        "MCP-Alchemy не доступен. "
        f"Пробовали: {', '.join((_ENV_VAR,) if _ENV_VAR else () + _CANDIDATES)}"
    )

# ─── публичные wrappers ───────────────────────────────────────────────────
def _post(endpoint: str, payload: dict) -> dict:
    url = f"{_discover_url()}{endpoint}"
    r   = requests.post(url, json=payload, timeout=10)
    r.raise_for_status()
    return r.json()

def query(sql: str) -> list[dict]:
    """SELECT-запрос, возвращает list[dict]."""
    return _post("/mcp/v1/query", {"query": sql}).get("rows", [])

def execute(sql: str) -> int:
    """INSERT/UPDATE/DELETE, возвращает изменённые строки."""
    return _post("/mcp/v1/execute", {"query": sql}).get("rowcount", 0)
