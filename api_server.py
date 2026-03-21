# api_server.py - 支援多交易所切換
import os
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional
from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import pyodbc

# ==============================
# 設定 Logger（使用 RotatingFileHandler）
# ==============================
os.makedirs("logs", exist_ok=True)

# 建立 RotatingFileHandler
file_handler = RotatingFileHandler(
    "logs/api_server.log",
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5,           # 保留 5 個備份
    encoding='utf-8'
)

# Console handler
console_handler = logging.StreamHandler()

# 設定格式
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# 設定 root logger
logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler]
)

log = logging.getLogger(__name__)
log.info("💾 API Server Log 設定完成 (最多 10MB × 6 個)")

# MSSQL 設定
MSSQL_SERVER   = os.getenv("MSSQL_SERVER",   "host.docker.internal")
MSSQL_DATABASE = os.getenv("MSSQL_DATABASE", "Crypto")
MSSQL_USER     = os.getenv("MSSQL_USER",     "sa")
MSSQL_PASSWORD = os.getenv("MSSQL_PASSWORD", "1qaz2WSX")

# 支援的交易所配置
EXCHANGES = {
    "bybit": {"name": "Bybit", "display_name": "Bybit Market Monitor", "db_table": "Bybit"},
    "binance": {"name": "Binance", "display_name": "Binance Market Monitor", "db_table": "Binance"},
    "okx": {"name": "OKX", "display_name": "OKX Market Monitor", "db_table": "OKX"},
}

app = FastAPI(title="Multi-Exchange Monitor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

def get_conn():
    return pyodbc.connect(
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={MSSQL_SERVER};"
        f"DATABASE={MSSQL_DATABASE};"
        f"UID={MSSQL_USER};"
        f"PWD={MSSQL_PASSWORD};"
        f"Encrypt=no;TrustServerCertificate=yes;",
        autocommit=True
    )

# ==============================
# API：取得所有可用交易所清單
# ==============================
@app.get("/api/exchanges")
def get_exchanges():
    """回傳所有支援的交易所清單"""
    return JSONResponse(content={
        "success": True,
        "exchanges": [
            {"id": k, **v} for k, v in EXCHANGES.items()
        ]
    })

# ==============================
# API：查詢市場資料（需指定交易所）
# ==============================
@app.get("/api/data")
def get_data(
    exchange: str           = Query(...,    description="交易所 ID (bybit/binance/okx)"),
    symbol:   Optional[str] = Query(None,   description="幣種"),
    minutes:  int           = Query(5,      description="最近幾分鐘"),
    limit:    int           = Query(500,    description="最多回傳幾筆"),
):
    """查詢指定交易所的市場資料"""
    if exchange not in EXCHANGES:
        return JSONResponse(status_code=400, content={
            "success": False, 
            "error": f"不支援的交易所: {exchange}"
        })
    
    try:
        conn   = get_conn()
        cursor = conn.cursor()

        where_clauses = ["[Time] >= DATEADD(MINUTE, ?, GETDATE())"]
        params        = [-minutes]

        if symbol and symbol != "ALL":
            where_clauses.append("Symbol = ?")
            params.append(symbol)

        where_sql = " AND ".join(where_clauses)
        table_name = EXCHANGES[exchange]["db_table"]

        exchange_prefix = EXCHANGES[exchange]["name"]  # Bybit / Binance / OKX

        spot_bids_col = f"{exchange_prefix}spot_bids"
        spot_asks_col = f"{exchange_prefix}spot_asks"

        contract_bids_col = f"{exchange_prefix}Contract_bids"
        contract_asks_col = f"{exchange_prefix}Contract_asks"

        sql = f"""
            SELECT TOP (?)
                [Time], Symbol,
                {spot_bids_col} AS Spot_bids,
                {spot_asks_col} AS Spot_asks,
                {contract_bids_col} AS Contract_bids,
                {contract_asks_col} AS Contract_asks,
                Open_position_Gap, Close_position_Gap,
                Open_position_Gap2nd, Close_position_Gap2nd
            FROM [dbo].[{table_name}]
            WHERE {where_sql}
            ORDER BY [Time] DESC
        """
        params = [limit] + params

        cursor.execute(sql, params)
        columns = [col[0] for col in cursor.description]
        rows    = cursor.fetchall()
        conn.close()

        result = []
        for row in rows:
            record = {}
            for i, col in enumerate(columns):
                val = row[i]
                if hasattr(val, 'strftime'):
                    val = val.strftime("%Y-%m-%d %H:%M:%S")
                elif val is not None:
                    try:
                        val = float(val)
                    except (TypeError, ValueError):
                        pass
                record[col] = val
            result.append(record)

        return JSONResponse(content={
            "success": True, 
            "exchange": exchange,
            "count": len(result), 
            "data": result
        })

    except Exception as e:
        log.error(f"API /api/data 錯誤：{e}")
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


# ==============================
# API：查詢指定交易所的幣種清單
# ==============================
@app.get("/api/symbols")
def get_symbols(exchange: str = Query(..., description="交易所 ID")):
    """查詢指定交易所的可用幣種"""
    if exchange not in EXCHANGES:
        return JSONResponse(status_code=400, content={
            "success": False,
            "error": f"不支援的交易所: {exchange}"
        })
    
    try:
        conn   = get_conn()
        cursor = conn.cursor()
        table_name = EXCHANGES[exchange]["db_table"]
        cursor.execute(f"SELECT DISTINCT Symbol FROM [dbo].[{table_name}] ORDER BY Symbol")
        symbols = [row[0] for row in cursor.fetchall()]
        conn.close()
        return JSONResponse(content={
            "success": True, 
            "exchange": exchange,
            "symbols": symbols
        })
    except Exception as e:
        log.error(f"API /api/symbols 錯誤：{e}")
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


# ==============================
# API：健康檢查
# ==============================
@app.get("/api/health")
def health():
    try:
        conn = get_conn()
        conn.close()
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "error", "db": str(e)})


# ==============================
# 提供前端靜態頁面
# ==============================
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def root():
    return FileResponse("static/dashboard.html")
