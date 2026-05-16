import logging
import os
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from binance_api import router as binance_router
from bybit_api import router as bybit_router
from exchange_api_common import EXCHANGES, get_conn
from okx_api import router as okx_router


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
