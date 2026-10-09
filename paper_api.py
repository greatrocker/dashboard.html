from typing import Literal, Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from exchange_api_common import DEFAULT_COLUMNS, EXCHANGES, _serialize_rows, get_conn


router = APIRouter(prefix="/api/paper", tags=["Paper Trading"])

Scope = Literal["single", "cross"]


def _filters(scope=None, symbol=None, exchange=None):
    """single = 現貨端與合約端同一家交易所；cross = 跨交易所。"""
    clauses, params = [], []
    if scope == "single":
        clauses.append("[BaseExchange] = [TargetExchange]")
    elif scope == "cross":
        clauses.append("[BaseExchange] <> [TargetExchange]")
    if symbol:
        clauses.append("[Symbol] = ?")
        params.append(symbol)
    if exchange:
        clauses.append("(? IN ([BaseExchange], [TargetExchange]))")
        params.append(exchange)
    return clauses, params


@router.get("/summary")
def paper_summary(
    scope: Optional[Scope] = Query(None, description="single / cross"),
    symbol: Optional[str] = Query(None),
    exchange: Optional[str] = Query(None),
):
    clauses, params = _filters(scope, symbol, exchange)
    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT
                SUM(CASE WHEN [Status] = 'OPEN' THEN 1 ELSE 0 END)                       AS OpenCount,
                SUM(CASE WHEN [Status] = 'OPEN' THEN [CostUsd] ELSE 0 END)                AS OpenCostUsd,
                SUM(CASE WHEN [Status] = 'OPEN' THEN ISNULL([UnrealizedPnl], 0) ELSE 0 END) AS UnrealizedPnl,
                SUM(CASE WHEN [Status] = 'CLOSED' THEN 1 ELSE 0 END)                     AS ClosedCount,
                SUM(CASE WHEN [Status] = 'CLOSED' THEN [NetPnl] ELSE 0 END)              AS RealizedPnl,
                SUM(CASE WHEN [Status] = 'CLOSED' THEN [GrossPnl] ELSE 0 END)            AS RealizedGross,
                SUM(CASE WHEN [Status] = 'CLOSED' THEN [EntryFee] + [ExitFee] ELSE 0 END) AS RealizedFees,
                SUM(CASE WHEN [Status] = 'CLOSED' AND [NetPnl] > 0 THEN 1 ELSE 0 END)    AS WinCount,
                AVG(CASE WHEN [Status] = 'CLOSED' THEN [NetPnlPct] END)                  AS AvgNetPct,
                AVG(CASE WHEN [Status] = 'CLOSED' THEN CAST(DATEDIFF(SECOND, [OpenedAt], [ClosedAt]) AS FLOAT) END)
                                                                                          AS AvgHoldSeconds,
                SUM(CASE WHEN [ExitReason] = 'TAKE_PROFIT' THEN 1 ELSE 0 END)            AS TakeProfitCount,
                SUM(CASE WHEN [ExitReason] = 'MEAN_REVERT' THEN 1 ELSE 0 END)            AS MeanRevertCount
            FROM [dbo].[PaperTrades] {where_sql}
            """,
            params,
        )
        row = _serialize_rows(cursor)[0]
        row = {k: (0 if v is None and k not in ("AvgNetPct", "AvgHoldSeconds") else v) for k, v in row.items()}
        row["WinRate"] = (row["WinCount"] / row["ClosedCount"] * 100) if row["ClosedCount"] else None
        return {"success": True, "summary": row}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})
    finally:
        conn.close()


def _raw_row(cursor, exchange_id, symbol, data_time):
    """訊號那一秒、該交易所資料表的原始行情列（現貨 Bid/Ask、合約 Bid/Ask）。"""
    exchange = EXCHANGES.get(exchange_id)
    if exchange is None or data_time is None:
        return None
    cols = exchange.get("columns", DEFAULT_COLUMNS)
    cursor.execute(
        f"SELECT [Time], {cols['spot_bids']}, {cols['spot_asks']}, {cols['contract_bids']}, {cols['contract_asks']}, "
        f"[Open_position_Gap], [Close_position_Gap] "
        f"FROM [dbo].[{exchange['db_table']}] WHERE [Symbol] = ? AND [Time] = ?",
        [symbol, data_time],
    )
    r = cursor.fetchone()
    if r is None:
        return None
    f = lambda v: None if v is None else float(v)
    return {"table": f"dbo.{exchange['db_table']}", "Time": r[0].strftime("%Y-%m-%d %H:%M:%S"),
            "SpotBid": f(r[1]), "SpotAsk": f(r[2]), "ContractBid": f(r[3]), "ContractAsk": f(r[4]),
            "OpenGap": f(r[5]), "CloseGap": f(r[6])}


@router.get("/triggers")
def paper_triggers(
    scope: Optional[Scope] = Query(None, description="single / cross"),
    symbol: Optional[str] = Query(None),
    exchange: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """每筆模擬交易的觸發依據：強力買訊號 + 訊號那一秒兩邊交易所的原始行情列（raw data）+ 實際成交。"""
    clauses, params = _filters(scope, symbol, exchange)
    clauses = [c.replace("[BaseExchange]", "t.[BaseExchange]").replace("[TargetExchange]", "t.[TargetExchange]")
               .replace("[Symbol]", "t.[Symbol]") for c in clauses]
    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT TOP (?) t.[Id] AS TradeId, t.[Status], t.[Symbol], t.[BaseExchange], t.[TargetExchange],
                   t.[OpenedAt], t.[ClosedAt], t.[Qty], t.[CostUsd], t.[EntrySpotPrice], t.[EntryContractPrice],
                   t.[EntryOpenGap], t.[ExitReason], t.[NetPnl], t.[NetPnlPct],
                   t.[ExitSpotPrice], t.[ExitContractPrice], t.[ExitDecidedAt], t.[ExitRefSpotBid], t.[ExitRefContractAsk],
                   s.[Id] AS SignalId, s.[DetectedAt], s.[DataTime], s.[WindowMinutes], s.[OpenGap], s.[AvgOpenGap],
                   s.[Deviation], s.[BaseSpotAsk], s.[TargetContractBid], s.[CapacityUsd], s.[CapacityQty], s.[RoundTripPct],
                   s.[SpotSpreadPct], s.[ContractSpreadPct]
            FROM [dbo].[PaperTrades] t
            LEFT JOIN [dbo].[StrongBuySignals] s ON s.[Id] = t.[SignalId]
            {where_sql}
            ORDER BY t.[OpenedAt] DESC
            """,
            [limit] + params,
        )
        rows = _serialize_rows(cursor)
        for row in rows:
            dt = row["DataTime"]
            row["RawBase"] = _raw_row(cursor, row["BaseExchange"], row["Symbol"], dt)
            row["RawTarget"] = _raw_row(cursor, row["TargetExchange"], row["Symbol"], dt)
            # 用原始行情重算訊號當下的 Open Gap（B 合約 Bid vs A 現貨 Ask），驗證訊號有依據
            b, t = row["RawBase"], row["RawTarget"]
            row["RawOpenGap"] = ((t["ContractBid"] - b["SpotAsk"]) / b["SpotAsk"] * 100
                                 if b and t and b["SpotAsk"] and t["ContractBid"] is not None else None)
        return {"success": True, "count": len(rows), "data": rows}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})
    finally:
        conn.close()


@router.get("/trades")
def paper_trades(
    status: Literal["open", "closed"] = Query("open"),
    scope: Optional[Scope] = Query(None, description="single / cross"),
    symbol: Optional[str] = Query(None),
    exchange: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    clauses, params = _filters(scope, symbol, exchange)
    clauses.insert(0, "[Status] = ?")
    params.insert(0, status.upper())
    order = "[OpenedAt] DESC" if status == "open" else "[ClosedAt] DESC"
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT TOP (?) [Id], [SignalId], [Symbol], [BaseExchange], [TargetExchange], [Status], [Qty],
                   [OpenedAt], [EntrySpotPrice], [EntryContractPrice], [EntryOpenGap], [EntryAvgOpenGap],
                   [EntryFee], [CostUsd], [MarkTime], [MarkSpotBid], [MarkContractAsk], [UnrealizedPnl],
                   [UnrealizedPct], [ClosedAt], [ExitReason], [ExitSpotPrice], [ExitContractPrice], [ExitFee],
                   [GrossPnl], [NetPnl], [NetPnlPct], [ExitFillSource],
                   DATEDIFF(SECOND, [OpenedAt], ISNULL([ClosedAt], GETDATE())) AS [HoldSeconds]
            FROM [dbo].[PaperTrades]
            WHERE {" AND ".join(clauses)}
            ORDER BY {order}
            """,
            [limit] + params,
        )
        rows = _serialize_rows(cursor)
        return {"success": True, "count": len(rows), "data": rows}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})
    finally:
        conn.close()
