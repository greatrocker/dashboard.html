import os
from typing import Optional

import pyodbc
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse


MSSQL_SERVER = os.getenv("MSSQL_SERVER", "host.docker.internal")
MSSQL_DATABASE = os.getenv("MSSQL_DATABASE", "Crypto")
MSSQL_USER = os.getenv("MSSQL_USER", "sa")
MSSQL_PASSWORD = os.getenv("MSSQL_PASSWORD", "1qaz2WSX")


EXCHANGES = {
    "bybit": {
        "name": "Bybit",
        "display_name": "Bybit Market Monitor",
        "db_table": "Bybit",
        "column_prefix": "Bybit",
    },
    "binance": {
        "name": "Binance",
        "display_name": "Binance Market Monitor",
        "db_table": "Binance",
        "column_prefix": "Binance",
    },
    "okx": {
        "name": "OKX",
        "display_name": "OKX Market Monitor",
        "db_table": "OKX",
        "column_prefix": "OKX",
    },
    "mexc": {
        "name": "MEXC",
        "display_name": "MEXC Market Monitor",
        "db_table": "MEXC",
        "column_prefix": "MEXC",
        "columns": {
            "spot_bids": "MEXCSpot_bids",
            "spot_asks": "MEXCSpot_asks",
            "contract_bids": "MEXContract_bids",
            "contract_asks": "MEXContract_asks",
        },
    },
}


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
    prefix = exchange["column_prefix"]
    columns = exchange.get("columns", {
        "spot_bids": f"{prefix}spot_bids",
        "spot_asks": f"{prefix}spot_asks",
        "contract_bids": f"{prefix}Contract_bids",
        "contract_asks": f"{prefix}Contract_asks",
    })

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
            table_name = exchange['db_table']
            prefix = exchange['column_prefix']
            columns = exchange.get("columns", {
                "spot_bids": f"{prefix}spot_bids",
                "spot_asks": f"{prefix}spot_asks",
            })

            sql = f"""
                SELECT TOP (?)
                    [Time],
                    {columns["spot_bids"]} AS Spot_bids,
                    {columns["spot_asks"]} AS Spot_asks
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
