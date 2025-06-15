"""
run_mcp.py  –  FastMCP-Lite (совместим и с /v1/*, и с /mcp/v1/*)
"""
import os, re, psycopg, uvicorn
from fastapi import FastAPI, APIRouter
from pydantic import BaseModel

RAW_DSN = os.getenv("DB_URL","postgresql+psycopg://crypto:secret@postgres:5432/crypto")
DB_DSN  = re.sub(r"\+[^:]+://", "://", RAW_DSN, 1)
PORT    = int(os.getenv("PORT", 3333))

conn = psycopg.connect(DB_DSN); conn.autocommit = True
app  = FastAPI(title="FastMCP-Lite")

class SQL(BaseModel):
    query: str

def add_routes(router: APIRouter):
    @router.post("/v1/query")
    def sql_query(payload: SQL):
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(payload.query)
            return {"rows": cur.fetchall(), "rowcount": cur.rowcount}

    @router.post("/v1/execute")
    def sql_execute(payload: SQL):
        with conn.cursor() as cur:
            cur.execute(payload.query)
            return {"rowcount": cur.rowcount}

# ── /v1/*  (короткий путь)
add_routes(app)

# ── /mcp/v1/*  (для старого клиента)
mcp_router = APIRouter(prefix="/mcp")
add_routes(mcp_router)
app.include_router(mcp_router)

if __name__ == "__main__":                          
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
