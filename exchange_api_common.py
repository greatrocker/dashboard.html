import os
from collections import defaultdict
from typing import Optional

import pyodbc
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse


MSSQL_SERVER = os.getenv("MSSQL_SERVER", "host.docker.internal")
MSSQL_DATABASE = os.getenv("MSSQL_DATABASE", "Crypto")
MSSQL_USER = os.getenv("MSSQL_USER", "sa")
MSSQL_PASSWORD = os.getenv("MSSQL_PASSWORD", "")   # 由 .env 提供，不在程式碼中寫死


# 欄位名稱依 README / sql_setup_all.sql；只有 Gate 的 Table 使用自己的欄位命名
DEFAULT_COLUMNS = {
    "spot_bids": "Spot_bids",
    "spot_asks": "Spot_asks",
    "contract_bids": "Contract_bids",
    "contract_asks": "Contract_asks",
}

EXCHANGES = {
    "bybit": {
        "name": "Bybit",
        "display_name": "Bybit Market Monitor",
        "db_table": "Bybit",
    },
    "binance": {
        "name": "Binance",
        "display_name": "Binance Market Monitor",
        "db_table": "Binance",
    },
    "okx": {
        "name": "OKX",
        "display_name": "OKX Market Monitor",
        "db_table": "OKX",
    },
    "mexc": {
        "name": "MEXC",
        "display_name": "MEXC Market Monitor",
        "db_table": "MEXC",
    },
    "gate": {
        "name": "Gate.io",
        "display_name": "Gate.io Market Monitor",
        "db_table": "Gate",
        "columns": {
            "spot_bids": "GateSpot_bids",
            "spot_asks": "GateSpot_asks",
            "contract_bids": "GateContract_bids",
            "contract_asks": "GateContract_asks",
        },
    },
}

# 前 20 大擴充的 15 家交易所（Table 結構同 Bybit，欄位用 DEFAULT_COLUMNS）
for _id, _name, _table in [
    ("bitget", "Bitget", "Bitget"),
    ("kucoin", "KuCoin", "KuCoin"),
    ("htx", "HTX", "HTX"),
    ("bingx", "BingX", "BingX"),
    ("cryptocom", "Crypto.com", "CryptoCom"),
    ("kraken", "Kraken", "Kraken"),
    ("coinbase", "Coinbase", "Coinbase"),
    ("bitfinex", "Bitfinex", "Bitfinex"),
    ("whitebit", "WhiteBIT", "WhiteBIT"),
    ("xt", "XT.com", "XT"),
    ("phemex", "Phemex", "Phemex"),
    ("poloniex", "Poloniex", "Poloniex"),
    ("deepcoin", "Deepcoin", "Deepcoin"),
    ("toobit", "Toobit", "Toobit"),
    ("pionex", "Pionex", "Pionex"),
]:
    EXCHANGES[_id] = {"name": _name, "display_name": f"{_name} Market Monitor", "db_table": _table}


def get_conn():
    return pyodbc.connect(
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={MSSQL_SERVER};"
        f"DATABASE={MSSQL_DATABASE};"
        f"UID={MSSQL_USER};"
        f"PWD={MSSQL_PASSWORD};"
        "Encrypt=no;TrustServerCertificate=yes;",
        autocommit=True,
    )


def _serialize_rows(cursor):
    columns = [col[0] for col in cursor.description]
    rows = cursor.fetchall()

    result = []
    for row in rows:
        record = {}
        for i, col in enumerate(columns):
            val = row[i]
            if hasattr(val, "strftime"):
                val = val.strftime("%Y-%m-%d %H:%M:%S")
            elif val is not None:
                try:
                    val = float(val)
                except (TypeError, ValueError):
                    pass
            record[col] = val
        result.append(record)
    return result


def query_market_data(exchange_id: str, symbol: Optional[str], minutes: int, limit: int):
    exchange = EXCHANGES[exchange_id]
    table_name = exchange["db_table"]
    columns = exchange.get("columns", DEFAULT_COLUMNS)

    where_clauses = ["[Time] >= DATEADD(MINUTE, ?, GETDATE())"]
    params = [-minutes]

    if symbol and symbol != "ALL":
        where_clauses.append("Symbol = ?")
        params.append(symbol)

    where_sql = " AND ".join(where_clauses)

    sql = f"""
        SELECT TOP (?)
            [Time], Symbol,
            {columns["spot_bids"]} AS Spot_bids,
            {columns["spot_asks"]} AS Spot_asks,
            {columns["contract_bids"]} AS Contract_bids,
            {columns["contract_asks"]} AS Contract_asks,
            Open_position_Gap, Close_position_Gap,
            Open_position_Gap2nd, Close_position_Gap2nd
        FROM [dbo].[{table_name}]
        WHERE {where_sql}
        ORDER BY [Time] DESC
    """

    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, [limit] + params)
        return _serialize_rows(cursor)
    finally:
        conn.close()



def query_multi_exchange_data(exchange_ids: list, symbol: str, minutes: int, limit: int):
    results = {}
    conn = get_conn()
    try:
        for eid in exchange_ids:
            if eid not in EXCHANGES:
                continue
            exchange = EXCHANGES[eid]
            table_name = exchange["db_table"]
            columns = exchange.get("columns", DEFAULT_COLUMNS)

            sql = f"""
                SELECT TOP (?)
                    [Time],
                    {columns["spot_bids"]} AS Spot_bids,
                    {columns["spot_asks"]} AS Spot_asks,
                    {columns["contract_bids"]} AS Contract_bids,
                    {columns["contract_asks"]} AS Contract_asks
                FROM [dbo].[{table_name}]
                WHERE Symbol = ? AND [Time] >= DATEADD(MINUTE, ?, GETDATE())
                ORDER BY [Time] DESC
            """
            cursor = conn.cursor()
            cursor.execute(sql, [limit, symbol, -minutes])
            results[eid] = _serialize_rows(cursor)
        return results
    finally:
        conn.close()

def query_spread_alert(exchange_ids: list, symbol: str, minutes: int):
    conn = get_conn()
    try:
        latest_asks = {}
        ts_data = {}

        for eid in exchange_ids:
            if eid not in EXCHANGES:
                continue
            exchange = EXCHANGES[eid]
            table_name = exchange["db_table"]
            columns = exchange.get("columns", DEFAULT_COLUMNS)
            ask_col = columns["spot_asks"]

            # 只取查詢區間內的最新價：Ticker 停掉或沒有這個幣的交易所不列入比較
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT TOP 1 {ask_col} FROM [dbo].[{table_name}] "
                f"WHERE Symbol = ? AND [Time] >= DATEADD(MINUTE, ?, GETDATE()) ORDER BY [Time] DESC",
                [symbol, -minutes],
            )
            row = cursor.fetchone()
            if row and row[0] is not None:
                latest_asks[eid] = float(row[0])

            cursor.execute(
                f"SELECT [Time], {ask_col} FROM [dbo].[{table_name}] "
                f"WHERE Symbol = ? AND [Time] >= DATEADD(MINUTE, ?, GETDATE()) ORDER BY [Time]",
                [symbol, -minutes],
            )
            ts_data[eid] = [
                (r[0], float(r[1])) for r in cursor.fetchall() if r[1] is not None
            ]

        if len(latest_asks) < 2:
            return {"error": "insufficient exchange data", "is_alert": False}

        asks = list(latest_asks.values())
        current_spread_pct = (max(asks) - min(asks)) / min(asks) * 100

        buckets = defaultdict(dict)
        for eid, rows in ts_data.items():
            for t, ask in rows:
                key = t.replace(second=(t.second // 10) * 10, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
                buckets[key][eid] = ask

        spreads = []
        for bucket_asks in buckets.values():
            if len(bucket_asks) >= 2:
                v = list(bucket_asks.values())
                spreads.append((max(v) - min(v)) / min(v) * 100)

        avg_spread_pct = sum(spreads) / len(spreads) if spreads else current_spread_pct
        max_eid = max(latest_asks, key=lambda k: latest_asks[k])
        min_eid = min(latest_asks, key=lambda k: latest_asks[k])

        return {
            "symbol": symbol,
            "current_spread_pct": round(current_spread_pct, 4),
            "avg_spread_pct": round(avg_spread_pct, 4),
            "is_alert": current_spread_pct > avg_spread_pct,
            "latest_asks": {eid: round(ask, 4) for eid, ask in latest_asks.items()},
            "highest_ask_exchange": max_eid,
            "lowest_ask_exchange": min_eid,
            "data_points": len(spreads),
        }
    finally:
        conn.close()


def query_symbols(exchange_id: str):
    table_name = EXCHANGES[exchange_id]["db_table"]
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT DISTINCT Symbol FROM [dbo].[{table_name}] ORDER BY Symbol")
        return [row[0] for row in cursor.fetchall()]
    finally:
        conn.close()


def build_exchange_router(exchange_id: str):
    exchange = EXCHANGES[exchange_id]
    router = APIRouter(prefix=f"/api/{exchange_id}", tags=[exchange["name"]])

    @router.get("/data")
    def get_data(
        symbol: Optional[str] = Query(None, description="幣種"),
        minutes: int = Query(5, description="最近幾分鐘"),
        limit: int = Query(500, description="最多回傳幾筆"),
    ):
        try:
            result = query_market_data(exchange_id, symbol, minutes, limit)
            return JSONResponse(
                content={
                    "success": True,
                    "exchange": exchange_id,
                    "count": len(result),
                    "data": result,
                }
            )
        except Exception as exc:
            return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})

    @router.get("/symbols")
    def get_symbols():
        try:
            symbols = query_symbols(exchange_id)
            return JSONResponse(content={"success": True, "exchange": exchange_id, "symbols": symbols})
        except Exception as exc:
            return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})

    return router
