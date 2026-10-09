from datetime import datetime
from typing import Literal, Optional

import pyodbc
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from exchange_api_common import EXCHANGES, _serialize_rows, get_conn


router = APIRouter(prefix="/api/signals", tags=["Signals"])


class StrongBuySignal(BaseModel):
    data_time: datetime = Field(..., description="觸發訊號的行情時間")
    symbol: str = Field(..., max_length=50)
    base_exchange: str = Field(..., description="現貨買入端交易所 ID")
    target_exchange: str = Field(..., description="合約賣出端交易所 ID")
    open_gap: float
    avg_open_gap: float
    deviation: float
    base_spot_ask: Optional[float] = None
    target_contract_bid: Optional[float] = None
    window_minutes: int = Field(..., ge=1, le=1440)


@router.post("")
def record_strong_buy(signal: StrongBuySignal):
    for exchange_id in (signal.base_exchange, signal.target_exchange):
        if exchange_id not in EXCHANGES:
            return JSONResponse(status_code=404, content={"success": False, "error": f"unknown exchange: {exchange_id}"})

    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO [dbo].[StrongBuySignals]
                ([DataTime], [Symbol], [BaseExchange], [TargetExchange], [OpenGap], [AvgOpenGap],
                 [Deviation], [BaseSpotAsk], [TargetContractBid], [WindowMinutes])
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [signal.data_time, signal.symbol, signal.base_exchange, signal.target_exchange,
             signal.open_gap, signal.avg_open_gap, signal.deviation,
             signal.base_spot_ask, signal.target_contract_bid, signal.window_minutes],
        )
        return {"success": True, "recorded": True}
    except pyodbc.IntegrityError:
        # 同一筆行情已被其他瀏覽器記錄過（UQ_StrongBuySignals_Event）
        return {"success": True, "recorded": False, "duplicate": True}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})
    finally:
        conn.close()


Scope = Literal["single", "cross"]


def _filters(symbol=None, min_deviation=None, min_open_gap=None, scope=None, exchange=None, window_minutes=None):
    """組出 WHERE 條件與參數。single = 現貨端與合約端同一家交易所。"""
    clauses, params = [], []
    if window_minutes is not None:
        clauses.append("[WindowMinutes] = ?")
        params.append(window_minutes)
    if symbol:
        clauses.append("[Symbol] = ?")
        params.append(symbol)
    if min_deviation is not None:
        clauses.append("[Deviation] >= ?")
        params.append(min_deviation)
    if min_open_gap is not None:
        clauses.append("[OpenGap] >= ?")
        params.append(min_open_gap)
    if scope == "single":
        clauses.append("[BaseExchange] = [TargetExchange]")
    elif scope == "cross":
        clauses.append("[BaseExchange] <> [TargetExchange]")
    if exchange:
        clauses.append("(? IN ([BaseExchange], [TargetExchange]))")
        params.append(exchange)
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


@router.get("/symbols")
def list_signal_symbols(
    min_deviation: Optional[float] = Query(None, ge=0, description="只計算偏離 >= 此值（百分點）的紀錄"),
    min_open_gap: Optional[float] = Query(None, description="只計算 Open Gap >= 此值（%）的紀錄"),
    scope: Optional[Scope] = Query(None, description="single：同一交易所現貨/合約；cross：跨交易所"),
    exchange: Optional[str] = Query(None, description="交易所 ID（現貨端或合約端）"),
    window_minutes: Optional[int] = Query(None, ge=1, description="均值區間（分鐘）"),
):
    """紀錄中出現過的幣種與筆數（給 Dashboard 幣種下拉選單用）。"""
    where_sql, params = _filters(min_deviation=min_deviation, min_open_gap=min_open_gap, scope=scope, exchange=exchange,
                                 window_minutes=window_minutes)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT [Symbol], COUNT(*) AS [Count] FROM [dbo].[StrongBuySignals] {where_sql} "
            f"GROUP BY [Symbol] ORDER BY [Symbol]",
            params,
        )
        return {"success": True, "symbols": [{"symbol": r[0], "count": r[1]} for r in cursor.fetchall()]}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})
    finally:
        conn.close()


@router.get("")
def list_strong_buys(
    limit: int = Query(100, ge=1, le=1000, description="最多回傳幾筆"),
    symbol: Optional[str] = Query(None, description="幣種（可選）"),
    min_deviation: Optional[float] = Query(None, ge=0, description="只回傳偏離 >= 此值（百分點）的紀錄"),
    min_open_gap: Optional[float] = Query(None, description="只回傳 Open Gap >= 此值（%）的紀錄"),
    scope: Optional[Scope] = Query(None, description="single：同一交易所現貨/合約；cross：跨交易所"),
    exchange: Optional[str] = Query(None, description="交易所 ID（現貨端或合約端）"),
    window_minutes: Optional[int] = Query(None, ge=1, description="均值區間（分鐘）"),
):
    where_sql, params = _filters(symbol=symbol, min_deviation=min_deviation, min_open_gap=min_open_gap,
                                 scope=scope, exchange=exchange, window_minutes=window_minutes)
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT TOP (?) [Id], [DetectedAt], [DataTime], [Symbol], [BaseExchange], [TargetExchange],
                   [OpenGap], [AvgOpenGap], [Deviation], [BaseSpotAsk], [TargetContractBid], [WindowMinutes],
                   [CapacityUsd], [CapacityQty], [RoundTripPct], [SpotSpreadPct], [ContractSpreadPct]
            FROM [dbo].[StrongBuySignals]
            {where_sql}
            ORDER BY [DetectedAt] DESC, [Id] DESC
            """,
            [limit] + params,
        )
        rows = _serialize_rows(cursor)
        return {"success": True, "count": len(rows), "data": rows}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})
    finally:
        conn.close()
