from typing import List
import logging
import os
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from binance_api import router as binance_router
from bybit_api import router as bybit_router
from exchange_api_common import EXCHANGES, get_conn, query_multi_exchange_data
from okx_api import router as okx_router
from mexc_api import router as mexc_router


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
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(bybit_router)
app.include_router(binance_router)
app.include_router(okx_router)
app.include_router(mexc_router)



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
@app.get("/api/exchanges")
def get_exchanges():
    return JSONResponse(
        content={
            "success": True,
            "exchanges": [{"id": exchange_id, **meta} for exchange_id, meta in EXCHANGES.items()],
        }
    )


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
    return FileResponse("static/dashboard.html")
