# -*- coding: utf-8 -*-
"""套利模擬交易（paper trading），由 signal_detector 驅動。

開倉：每筆新的強力買訊號，以即時訂單簿逐檔成交的結果開倉（數量 = 可套利幣量）
      A 所現貨：買進；B 所合約：放空。單一交易所時 A == B。
持倉：每秒用最新行情（A 所現貨 Bid、B 所合約 Ask）估算「現在平倉」的淨損益，每 MARK_INTERVAL 秒寫回 DB。
平倉：任一條件成立
      TAKE_PROFIT ：扣 4 筆手續費後淨損益 >= TAKE_PROFIT_PCT %
      MEAN_REVERT ：Open Gap（B 合約 Bid vs A 現貨 Ask）回到開倉時的 5 分鐘均值以下
      平倉時查即時訂單簿逐檔成交（賣現貨、買回合約）；訂單簿查不到才改用最新報價。
損益：Qty × (賣現貨均價 − 買現貨均價) + Qty × (放空均價 − 買回均價) − 手續費；報酬率以買現貨花費為分母。
"""
import logging
import os
import time
from dataclasses import dataclass, field

import pandas as pd

from orderbook_depth import fetch_book, walk_fill

SPOT_FEE = float(os.getenv("SPOT_FEE", "0.001"))            # 現貨 taker 0.1%
CONTRACT_FEE = float(os.getenv("CONTRACT_FEE", "0.0005"))   # 合約 taker 0.05%
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "0.1"))  # 淨損益 >= 0.1% 停利
MARK_INTERVAL = int(os.getenv("MARK_INTERVAL", "10"))       # 持倉估值寫回 DB 的間隔（秒）
QUOTE_STALE_SECONDS = int(os.getenv("STALE_SECONDS", "10"))

log = logging.getLogger("signal_detector")


@dataclass
class Position:
    id: int
    symbol: str
    base: str
    target: str
    qty: float
    entry_spot: float
    entry_contract: float
    entry_avg_gap: float
    entry_fee: float
    cost: float
    mark: tuple = field(default=None)   # (時間, 現貨 Bid, 合約 Ask, 淨損益, 淨報酬率)
    exit_ref: tuple = field(default=None)   # 平倉決策當下 (行情時間, 現貨 Bid, 合約 Ask)

    @property
    def key(self):
        return (self.base, self.target, self.symbol)


def fees(qty, spot_px, contract_px):
    return qty * spot_px * SPOT_FEE + qty * contract_px * CONTRACT_FEE


def close_pnl(pos, spot_exit, contract_exit):
    """以 (賣現貨價, 買回合約價) 平倉的 (毛利, 平倉手續費, 淨損益, 淨報酬率 %)。"""
    gross = pos.qty * (spot_exit - pos.entry_spot) + pos.qty * (pos.entry_contract - contract_exit)
    exit_fee = fees(pos.qty, spot_exit, contract_exit)
    net = gross - pos.entry_fee - exit_fee
    return gross, exit_fee, net, net / pos.cost * 100


def exit_reason(pos, spot_ask, spot_bid, contract_bid, contract_ask):
    """回傳平倉原因或 None。"""
    _, _, _, pct = close_pnl(pos, spot_bid, contract_ask)
    if pct >= TAKE_PROFIT_PCT:
        return "TAKE_PROFIT"
    if spot_ask and (contract_bid - spot_ask) / spot_ask * 100 <= pos.entry_avg_gap:
        return "MEAN_REVERT"
    return None


class PaperTrader:
    def __init__(self, executor):
        self.executor = executor     # 背景執行緒：平倉時查訂單簿
        self.positions = {}          # id -> Position
        self.closing = {}            # id -> future（正在查訂單簿平倉）
        self.last_mark = 0.0
        self.loaded = False

    # ---------- 開倉 ----------
    def load_open(self, cursor):
        """服務重啟時接回尚未平倉的部位。"""
        cursor.execute(
            "SELECT Id, Symbol, BaseExchange, TargetExchange, Qty, EntrySpotPrice, EntryContractPrice, "
            "EntryAvgOpenGap, EntryFee, CostUsd FROM dbo.PaperTrades WHERE Status = 'OPEN'"
        )
        for r in cursor.fetchall():
            pos = Position(int(r[0]), r[1], r[2], r[3], *(float(x) for x in r[4:10]))
            self.positions[pos.id] = pos
        self.loaded = True
        if self.positions:
            log.info(f"Paper trading: resumed {len(self.positions)} open positions")

    def has_open(self, key):
        return any(p.key == key for p in self.positions.values())

    def open(self, cursor, signal_id, key, signal, fill):
        """fill = (買現貨花費 USDT, 幣量, 放空合約收到 USDT)，來自即時訂單簿逐檔配對。"""
        spot_usd, qty, contract_usd = fill
        if qty <= 0 or self.has_open(key):
            return None   # 同一組合已有持倉中部位就不重複開倉
        base, target, symbol = key
        entry_spot, entry_contract = spot_usd / qty, contract_usd / qty
        entry_gap = (entry_contract - entry_spot) / entry_spot * 100
        entry_fee = fees(qty, entry_spot, entry_contract)
        cursor.execute(
            """
            INSERT INTO dbo.PaperTrades
                (SignalId, Symbol, BaseExchange, TargetExchange, Status, Qty, EntrySpotPrice, EntryContractPrice,
                 EntryOpenGap, EntryAvgOpenGap, EntryFee, CostUsd)
            OUTPUT INSERTED.Id
            VALUES (?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, ?, ?, ?)
            """,
            [signal_id, symbol, base, target, qty, entry_spot, entry_contract, round(entry_gap, 6),
             signal["avg_open_gap"], round(entry_fee, 6), round(spot_usd, 2)],
        )
        pos = Position(int(cursor.fetchone()[0]), symbol, base, target, qty, entry_spot, entry_contract,
                       signal["avg_open_gap"], entry_fee, spot_usd)
        self.positions[pos.id] = pos
        log.info(f"PAPER OPEN #{pos.id} {symbol} {base}->{target}: qty {qty:.6g}, spot {entry_spot:.6g}, "
                 f"short {entry_contract:.6g}, gap {entry_gap:+.4f}%, cost ${spot_usd:,.0f}")
        return pos.id

    # ---------- 每秒：估值、判斷平倉、完成平倉 ----------
    def step(self, cursor, quotes, latest_time):
        """quotes: {(交易所, 幣種): (時間, 現貨 Ask, 現貨 Bid, 合約 Bid, 合約 Ask)}"""
        self._finish_closing(cursor)
        if latest_time is None:
            return
        stale_limit = latest_time - pd.Timedelta(seconds=QUOTE_STALE_SECONDS)
        for pos in self.positions.values():
            if pos.id in self.closing:
                continue
            spot, contract = quotes.get((pos.base, pos.symbol)), quotes.get((pos.target, pos.symbol))
            if not spot or not contract or spot[0] < stale_limit or contract[0] < stale_limit:
                continue   # 行情缺漏或過時：先不估值、不平倉
            _, spot_ask, spot_bid, _, _ = spot
            _, _, _, contract_bid, contract_ask = contract
            if None in (spot_bid, contract_ask) or spot_bid != spot_bid or contract_ask != contract_ask:
                continue
            _, _, net, pct = close_pnl(pos, spot_bid, contract_ask)
            pos.mark = (max(spot[0], contract[0]).to_pydatetime(), spot_bid, contract_ask, net, pct)
            reason = exit_reason(pos, spot_ask, spot_bid, contract_bid, contract_ask)
            if reason:
                # 記下平倉決策當下的參考報價與時間，平倉成交後用來算執行滑價
                pos.exit_ref = (pos.mark[0], spot_bid, contract_ask)
                self.closing[pos.id] = self.executor.submit(self._exit_fill, pos, reason, spot_bid, contract_ask)
        if time.time() - self.last_mark >= MARK_INTERVAL:
            self._write_marks(cursor)
            self.last_mark = time.time()

    def _exit_fill(self, pos, reason, quote_spot_bid, quote_contract_ask):
        """背景執行：查即時訂單簿逐檔成交平倉；失敗改用最新報價。"""
        try:
            spot_bids = fetch_book(pos.base, "spot", pos.symbol)[0]
            contract_asks = fetch_book(pos.target, "contract", pos.symbol)[1]
            spot_px, _ = walk_fill(spot_bids, pos.qty)
            contract_px, _ = walk_fill(contract_asks, pos.qty)
            if spot_px and contract_px:
                return reason, spot_px, contract_px, "BOOK"
        except Exception as exc:
            log.warning(f"Paper close #{pos.id} order book failed, using quotes: {exc}")
        return reason, quote_spot_bid, quote_contract_ask, "QUOTE"

    def _finish_closing(self, cursor):
        for pid, fut in list(self.closing.items()):
            if not fut.done():
                continue
            del self.closing[pid]
            pos = self.positions.pop(pid)
            reason, spot_px, contract_px, source = fut.result()
            gross, exit_fee, net, pct = close_pnl(pos, spot_px, contract_px)
            decided_at, ref_spot_bid, ref_contract_ask = pos.exit_ref
            cursor.execute(
                """
                UPDATE dbo.PaperTrades
                SET Status = 'CLOSED', ClosedAt = GETDATE(), ExitReason = ?, ExitSpotPrice = ?, ExitContractPrice = ?,
                    ExitFee = ?, GrossPnl = ?, NetPnl = ?, NetPnlPct = ?, ExitFillSource = ?,
                    ExitDecidedAt = ?, ExitRefSpotBid = ?, ExitRefContractAsk = ?
                WHERE Id = ?
                """,
                [reason, spot_px, contract_px, round(exit_fee, 6), round(gross, 6), round(net, 6), round(pct, 6),
                 source, decided_at, ref_spot_bid, ref_contract_ask, pid],
            )
            log.info(f"PAPER CLOSE #{pid} {pos.symbol} {pos.base}->{pos.target} [{reason}/{source}]: "
                     f"net {net:+,.2f} USDT ({pct:+.4f}%), gross {gross:+,.2f}, fees {pos.entry_fee + exit_fee:,.2f}")

    def _write_marks(self, cursor):
        for pos in self.positions.values():
            if pos.mark and pos.id not in self.closing:
                t, sb, ca, net, pct = pos.mark
                cursor.execute(
                    "UPDATE dbo.PaperTrades SET MarkTime = ?, MarkSpotBid = ?, MarkContractAsk = ?, "
                    "UnrealizedPnl = ?, UnrealizedPct = ? WHERE Id = ? AND Status = 'OPEN'",
                    [t, sb, ca, round(net, 6), round(pct, 6), pos.id],
                )
