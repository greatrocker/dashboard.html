from typing import List, Optional
import importlib
import logging
import os
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from exchange_api_common import (
    EXCHANGES, get_conn, query_market_data, query_multi_exchange_data, query_spread_alert, query_symbols,
)
from signals_api import router as signals_router
from paper_api import router as paper_router


os.makedirs("logs", exist_ok=True)

file_handler = RotatingFileHandler(
    "logs/api_server.log",
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)
console_handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
log = logging.getLogger(__name__)
log.info("API Server Log initialized")

app = FastAPI(title="Multi-Exchange Monitor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# 每個交易所一個 <exchange_id>_api.py（例如 bybit_api.py），提供 /api/<exchange_id>/data 與 /symbols
for exchange_id in EXCHANGES:
    app.include_router(importlib.import_module(f"{exchange_id}_api").router)

# 跨交易所強力買訊號紀錄（POST 寫入 / GET 查詢）
app.include_router(signals_router)

# 套利模擬交易（signal-detector 寫入 dbo.PaperTrades）
app.include_router(paper_router)



@app.get("/api/multi/data")
def get_multi_data(
    exchanges: List[str] = Query(..., alias="exchange"),
    symbol: str = Query(..., description="幣種"),
    minutes: int = Query(5, description="最近幾分鐘"),
    limit: int = Query(500, description="最多幾筆"),
):
    try:
        result = query_multi_exchange_data(exchanges, symbol, minutes, limit)
        return JSONResponse(content={"success": True, "data": result})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})
@app.get("/api/spread/alert")
def get_spread_alert(
    exchanges: List[str] = Query(..., alias="exchange"),
    symbol: str = Query(...),
    minutes: int = Query(5),
):
    try:
        result = query_spread_alert(exchanges, symbol, minutes)
        return JSONResponse(content={"success": True, **result})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})


@app.get("/api/exchanges")
def get_exchanges():
    return JSONResponse(
        content={
            "success": True,
            "exchanges": [{"id": exchange_id, **meta} for exchange_id, meta in EXCHANGES.items()],
        }
    )


def _unknown_exchange(exchange: str):
    return JSONResponse(
        status_code=404,
        content={"success": False, "error": f"unknown exchange: {exchange}", "exchanges": list(EXCHANGES)},
    )


@app.get("/api/data")
def get_data(
    exchange: str = Query(..., description="交易所 ID"),
    symbol: Optional[str] = Query(None, description="幣種"),
    minutes: int = Query(5, description="最近幾分鐘"),
    limit: int = Query(500, description="最多回傳幾筆"),
):
    exchange = exchange.lower()
    if exchange not in EXCHANGES:
        return _unknown_exchange(exchange)
    try:
        result = query_market_data(exchange, symbol, minutes, limit)
        return JSONResponse(content={"success": True, "exchange": exchange, "count": len(result), "data": result})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})


@app.get("/api/symbols")
def get_symbols(exchange: str = Query(..., description="交易所 ID")):
    exchange = exchange.lower()
    if exchange not in EXCHANGES:
        return _unknown_exchange(exchange)
    try:
        return JSONResponse(content={"success": True, "exchange": exchange, "symbols": query_symbols(exchange)})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})


@app.get("/api/health")
def health():
    try:
        conn = get_conn()
        conn.close()
        return {"status": "ok", "db": "connected"}
    except Exception as exc:
        return JSONResponse(status_code=503, content={"status": "error", "db": str(exc)})


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def root():
    # no-cache：瀏覽器每次都向伺服器確認，Dashboard 更新後重新整理即可看到新版
    return FileResponse("static/dashboard.html", headers={"Cache-Control": "no-cache"})
