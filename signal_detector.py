# -*- coding: utf-8 -*-
"""強力買偵測（背景服務，24 小時執行），涵蓋單一交易所與跨交易所。

每秒對「所有交易所對（含同一交易所 A == B）× 所有幣種 × 多個均值區間」計算 Open Gap：
    Open Gap = (B 所合約 Bid − A 所現貨 Ask) / A 所現貨 Ask × 100
    偏離     = 最新 Open Gap − 最近 W 分鐘的平均 Open Gap（百分點）
    W = 5 分鐘：以逐秒行情精確計算（同一秒配對）
    W > 5 分鐘：以每分鐘平均價計算平均 Open Gap（24 小時逐秒資料太大，分鐘平均誤差可忽略）
偏離 > STRONG_BUY_DEV 且最新 Open Gap > MIN_OPEN_GAP → 候選；再查兩邊即時訂單簿：
    可套利金額 >= MIN_CAPACITY_USD，且獲利空間（Open Gap + Close Gap ≈ −兩邊買賣價差合計）>= MIN_ROUND_TRIP
才寫入 dbo.StrongBuySignals（每個組合 × 區間只在「進入」強力買時寫一筆）。
"""
import logging
import math
import os
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from logging.handlers import RotatingFileHandler

import numpy as np
import pandas as pd
import pyodbc
import requests

from exchange_api_common import DEFAULT_COLUMNS, EXCHANGES, get_conn
from orderbook_depth import arbitrage_capacity, fetch_book, preload_specs
from paper_trader import PaperTrader


WINDOW_MINUTES = int(os.getenv("WINDOW_MINUTES", "5"))      # 逐秒精確計算的區間（也是行情快取長度）
WINDOWS = sorted({WINDOW_MINUTES, *(int(w) for w in os.getenv("WINDOWS", "5,15,30,60,240,720,1440").split(","))})
LONG_WINDOWS = [w for w in WINDOWS if w > WINDOW_MINUTES]   # 以分鐘平均價計算的長區間
MAX_WINDOW = max(WINDOWS)
LONG_MIN_COVERAGE = float(os.getenv("LONG_MIN_COVERAGE", "0.5"))  # 長區間至少要有幾成的分鐘有資料
STRONG_BUY_DEV = float(os.getenv("STRONG_BUY_DEV", "0.5"))  # 強力買門檻（偏離，百分點）
MIN_OPEN_GAP = float(os.getenv("MIN_OPEN_GAP", "0.2"))      # 現在的 Open Gap 也要 > 此值（%），才是真的有利可圖
MIN_CAPACITY_USD = float(os.getenv("MIN_CAPACITY_USD", "1000"))  # 即時訂單簿可套利金額門檻（USDT）
MIN_ROUND_TRIP = float(os.getenv("MIN_ROUND_TRIP", "-0.3"))  # 獲利空間門檻（%）：兩邊買賣價差合計不能超過 0.3%
MAX_SPOT_SPREAD = float(os.getenv("MAX_SPOT_SPREAD", "0.1"))          # 現貨端 (Ask − Bid) / Bid 上限（%）
MAX_CONTRACT_SPREAD = float(os.getenv("MAX_CONTRACT_SPREAD", "0.1"))  # 合約端 (Ask − Bid) / Bid 上限（%）
RECHECK_SECONDS = int(os.getenv("RECHECK_SECONDS", "30"))   # 掛單不足 / 價差太大的組合幾秒後再查一次
BOOK_TIMEOUT = float(os.getenv("BOOK_TIMEOUT", "4.5"))      # 查訂單簿最多等幾秒（需小於 MAX_CHECK_AGE）
MAX_CHECK_AGE = float(os.getenv("MAX_CHECK_AGE", "5"))      # 送出查詢後超過幾秒還沒查到訂單簿 → 丟棄，不用過時訊號開倉
MAX_INFLIGHT = int(os.getenv("MAX_INFLIGHT", "20"))         # 同時查訂單簿的組合上限；有空位時依偏離大小優先補上
MIN_POINTS = int(os.getenv("MIN_POINTS", "30"))             # 5 分鐘區間至少幾筆配對資料才判斷
STALE_SECONDS = int(os.getenv("STALE_SECONDS", "10"))       # 最新配對行情落後超過幾秒就跳過（Ticker 停了）
PAPER_WINDOW = int(os.getenv("PAPER_WINDOW", "5"))          # 模擬交易只跟這個區間的訊號（避免同一機會重複開倉）
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "1"))
HEARTBEAT_PORT = int(os.getenv("HEARTBEAT_PORT", "9020"))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
LOG_DIR = "/app/logs"

EXCHANGE_IDS = list(EXCHANGES)
_book_pool = ThreadPoolExecutor(max_workers=16)       # 平行查訂單簿
_capacity_runner = ThreadPoolExecutor(max_workers=4)  # 背景跑「查訂單簿 → 算可套利金額」，不卡住偵測迴圈
_close_runner = ThreadPoolExecutor(max_workers=2)     # 模擬交易平倉專用，不跟候選訊號搶工作線
_backfill_runner = ThreadPoolExecutor(max_workers=1)  # 啟動時補回 24 小時分鐘資料

os.makedirs(LOG_DIR, exist_ok=True)
_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
_file_handler = RotatingFileHandler(f"{LOG_DIR}/signal_detector.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
_file_handler.setFormatter(_formatter)
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_formatter)
log = logging.getLogger("signal_detector")
log.setLevel(logging.INFO)
log.addHandler(_file_handler)
log.addHandler(_console_handler)


def window_label(minutes):
    return f"{minutes // 60}h" if minutes >= 60 and minutes % 60 == 0 else f"{minutes}m"


def heartbeat_server():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", HEARTBEAT_PORT))
    srv.listen(5)
    log.info(f"Heartbeat server on port {HEARTBEAT_PORT}")
    while True:
        try:
            conn, _ = srv.accept()
            conn.close()
        except Exception:
            pass


def send_telegram(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
            timeout=10,
        )
    except Exception as exc:
        log.warning(f"Telegram failed: {exc}")


PRICE_COLS = ["sa", "cb", "sb", "ca"]   # 現貨 Ask、合約 Bid（開倉側）、現貨 Bid、合約 Ask（平倉側）


class MarketWindow:
    """各交易所最近 WINDOW_MINUTES 分鐘的逐秒現貨/合約買賣價，第一次全抓、之後只抓新資料。"""

    def __init__(self):
        empty = pd.DataFrame(columns=["Time", "Symbol"] + PRICE_COLS)
        self.frames = {eid: empty.copy() for eid in EXCHANGE_IDS}
        self.last_time = {eid: None for eid in EXCHANGE_IDS}
        self.latest = None   # 所有交易所中最新的行情時間（用 DB 時間當時鐘，不受容器時區影響）

    def refresh(self, cursor):
        for eid in EXCHANGE_IDS:
            exchange = EXCHANGES[eid]
            cols = exchange.get("columns", DEFAULT_COLUMNS)
            if self.last_time[eid] is None:
                where, params = "[Time] >= DATEADD(MINUTE, ?, GETDATE())", [-WINDOW_MINUTES]
            else:
                # 含最後一秒：Ticker 同一秒的幣種是逐筆寫入的，上一輪可能只讀到一部分
                where, params = "[Time] >= ?", [self.last_time[eid]]
            cursor.execute(
                f"SELECT [Time], [Symbol], {cols['spot_asks']}, {cols['contract_bids']}, "
                f"{cols['spot_bids']}, {cols['contract_asks']} "
                f"FROM [dbo].[{exchange['db_table']}] WHERE {where}",
                params,
            )
            rows = cursor.fetchall()
            if not rows:
                continue
            new = pd.DataFrame.from_records([tuple(r) for r in rows], columns=["Time", "Symbol"] + PRICE_COLS)
            new[PRICE_COLS] = new[PRICE_COLS].astype(float)
            frame = pd.concat([self.frames[eid], new]) if len(self.frames[eid]) else new
            self.frames[eid] = frame.drop_duplicates(["Time", "Symbol"], keep="last")
            self.last_time[eid] = new["Time"].max().to_pydatetime()

        times = [f["Time"].max() for f in self.frames.values() if len(f)]
        if not times:
            return
        self.latest = max(times)
        cutoff = self.latest - pd.Timedelta(minutes=WINDOW_MINUTES)
        for eid, frame in self.frames.items():
            if len(frame):
                self.frames[eid] = frame[frame["Time"] >= cutoff]

    def wide(self):
        """回傳 (現貨 Ask, 合約 Bid) 兩張寬表：index=(Symbol, Time)、columns=交易所。"""
        parts = [f.assign(ex=eid) for eid, f in self.frames.items() if len(f)]
        if not parts:
            return None, None
        long = pd.concat(parts, ignore_index=True)
        spot_ask = long.pivot(index=["Symbol", "Time"], columns="ex", values="sa").reindex(columns=EXCHANGE_IDS)
        contract_bid = long.pivot(index=["Symbol", "Time"], columns="ex", values="cb").reindex(columns=EXCHANGE_IDS)
        return spot_ask.sort_index(), contract_bid.sort_index()

    def latest_quotes(self):
        """{(交易所, 幣種): (時間, 現貨 Ask, 現貨 Bid, 合約 Bid, 合約 Ask)}，各取最新一筆（模擬交易估值用）。"""
        quotes = {}
        for eid, frame in self.frames.items():
            if not len(frame):
                continue
            last = frame.sort_values("Time").groupby("Symbol").tail(1)
            for t, sym, sa, cb, sb, ca in last[["Time", "Symbol"] + PRICE_COLS].itertuples(index=False):
                quotes[(eid, sym)] = (t, sa, sb, cb, ca)
        return quotes


def _backfill_minutes():
    """背景執行：從 DB 讀過去 MAX_WINDOW 分鐘各交易所各幣的每分鐘平均（現貨 Ask、合約 Bid），不含目前這一分鐘。"""
    started = time.time()
    conn = get_conn()
    try:
        cursor = conn.cursor()
        parts = []
        for eid in EXCHANGE_IDS:
            exchange = EXCHANGES[eid]
            cols = exchange.get("columns", DEFAULT_COLUMNS)
            minute = "DATEADD(MINUTE, DATEDIFF(MINUTE, 0, [Time]), 0)"
            cursor.execute(
                f"SELECT [Symbol], {minute} AS [Minute], AVG(CAST({cols['spot_asks']} AS FLOAT)), "
                f"AVG(CAST({cols['contract_bids']} AS FLOAT)) "
                f"FROM [dbo].[{exchange['db_table']}] "
                f"WHERE [Time] >= DATEADD(MINUTE, ?, GETDATE()) "
                f"  AND [Time] < DATEADD(MINUTE, DATEDIFF(MINUTE, 0, GETDATE()), 0) "
                f"GROUP BY [Symbol], {minute}",
                [-MAX_WINDOW - 1],
            )
            rows = cursor.fetchall()
            if rows:
                df = pd.DataFrame.from_records([tuple(r) for r in rows], columns=["Symbol", "Minute", "sa", "cb"])
                parts.append(df.assign(ex=eid))
        result = pd.concat(parts, ignore_index=True) if parts else None
        return result, time.time() - started
    finally:
        conn.close()


class MinuteHistory:
    """各交易所各幣「每分鐘平均現貨 Ask / 合約 Bid」，保留 MAX_WINDOW 分鐘，用來算長區間的平均 Open Gap。"""

    def __init__(self):
        self.data = pd.DataFrame(columns=["ex", "Symbol", "Minute", "sa", "cb"])
        self.last_minute = None    # 最後一個已從即時行情彙整的分鐘
        self.backfill = None       # 背景補資料的 future
        self.ready = not LONG_WINDOWS
        self.means = {}            # {W: {symbol: (平均 Open Gap 矩陣, 分鐘數矩陣)}}
        self.means_at = None

    def start_backfill(self):
        if LONG_WINDOWS:
            self.backfill = _backfill_runner.submit(_backfill_minutes)

    def _merge(self, df, prefer_existing):
        if df is None or not len(df):
            return
        merged = pd.concat([self.data, df] if prefer_existing else [df, self.data], ignore_index=True)
        # prefer_existing：補回的資料不覆蓋已由即時行情彙整的分鐘
        self.data = merged.drop_duplicates(["ex", "Symbol", "Minute"], keep="first")

    def update(self, window):
        """每輪呼叫：接上背景補資料、彙整剛結束的分鐘、每分鐘重算一次長區間平均。回傳是否重算了平均。"""
        if self.backfill is not None and self.backfill.done():
            fut, self.backfill = self.backfill, None
            try:
                df, secs = fut.result()
                self._merge(df, prefer_existing=True)
                log.info(f"Minute history backfilled: {0 if df is None else len(df)} rows in {secs:.1f}s; "
                         f"long windows {', '.join(window_label(w) for w in LONG_WINDOWS)} enabled")
            except Exception as exc:
                log.error(f"Minute history backfill failed (long windows use live data only): {exc}")
            self.ready = True

        if window.latest is None:
            return False
        done_minute = window.latest.floor("min") - pd.Timedelta(minutes=1)   # 最後一個「已結束」的分鐘
        if self.last_minute is None:
            self.last_minute = done_minute - pd.Timedelta(minutes=1)
        if done_minute > self.last_minute:
            parts = []
            for eid, frame in window.frames.items():
                if not len(frame):
                    continue
                f = frame[(frame["Time"] > self.last_minute + pd.Timedelta(minutes=1) - pd.Timedelta(microseconds=1))
                          & (frame["Time"] < done_minute + pd.Timedelta(minutes=1))]
                if len(f):
                    g = f.assign(Minute=f["Time"].dt.floor("min")).groupby(["Symbol", "Minute"])[["sa", "cb"]].mean()
                    parts.append(g.reset_index().assign(ex=eid))
            if parts:
                self._merge(pd.concat(parts, ignore_index=True), prefer_existing=False)
            self.last_minute = done_minute
            cutoff = done_minute - pd.Timedelta(minutes=MAX_WINDOW)
            self.data = self.data[self.data["Minute"] > cutoff]
            if self.ready:
                self._recompute(done_minute)
                return True
        return False

    def _recompute(self, done_minute):
        """以分鐘平均價算各長區間、各組合的平均 Open Gap 與有效分鐘數。"""
        means = {w: {} for w in LONG_WINDOWS}
        if not len(self.data):
            self.means = means
            return
        sa = self.data.pivot_table(index=["Symbol", "Minute"], columns="ex", values="sa").reindex(columns=EXCHANGE_IDS)
        cb = self.data.pivot_table(index=["Symbol", "Minute"], columns="ex", values="cb").reindex(columns=EXCHANGE_IDS)
        for symbol in sa.index.get_level_values(0).unique():
            s, c = sa.loc[symbol], cb.loc[symbol]
            minutes = s.index.values
            sv, cv = s.to_numpy(dtype=float), c.to_numpy(dtype=float)
            with np.errstate(invalid="ignore", divide="ignore"):
                gap = (cv[:, None, :] - sv[:, :, None]) / sv[:, :, None] * 100
            valid = ~np.isnan(gap)
            filled = np.where(valid, gap, 0.0)
            for w in LONG_WINDOWS:
                sel = minutes > np.datetime64(done_minute - pd.Timedelta(minutes=w))
                count = valid[sel].sum(axis=0)
                means[w][symbol] = (filled[sel].sum(axis=0) / np.maximum(count, 1), count)
        self.means = means
        self.means_at = done_minute


def detect(window: MarketWindow, history: MinuteHistory = None):
    """回傳 (本輪有評估的組合 set, 目前強力買的組合 dict)。key = (base, target, symbol, 均值區間分鐘)。"""
    spot_ask, contract_bid = window.wide()
    if spot_ask is None:
        return set(), {}
    stale_limit = np.datetime64(window.latest - pd.Timedelta(seconds=STALE_SECONDS))
    long_means = history.means if history is not None and history.ready else {}
    evaluated, strong = set(), {}

    for symbol in spot_ask.index.get_level_values(0).unique():
        sa_frame, cb_frame = spot_ask.loc[symbol], contract_bid.loc[symbol]
        times = sa_frame.index.values
        sa, cb = sa_frame.to_numpy(dtype=float), cb_frame.to_numpy(dtype=float)
        with np.errstate(invalid="ignore", divide="ignore"):
            # gap[t, a, b] = A 所現貨買、B 所合約賣的 Open Gap %
            # 對角線 a == b 為單一交易所（同一家現貨買、自家合約賣），與跨交易所一起偵測
            gap = (cb[:, None, :] - sa[:, :, None]) / sa[:, :, None] * 100
        valid = ~np.isnan(gap)
        count = valid.sum(axis=0)
        mean = np.where(valid, gap, 0.0).sum(axis=0) / np.maximum(count, 1)
        last_idx = len(times) - 1 - valid[::-1].argmax(axis=0)            # 每個組合最新一筆配對
        current = np.take_along_axis(gap, last_idx[None, :, :], axis=0)[0]
        fresh = (times[last_idx] >= stale_limit) & (count > 0)
        # 偏離大但 Open Gap 仍為負（價差只是「從很差回升」）不算機會
        profitable = np.round(current, 4) > MIN_OPEN_GAP

        # 各區間的（平均 Open Gap, 是否樣本足夠）
        per_window = [(WINDOW_MINUTES, mean, count >= MIN_POINTS)]
        for w in LONG_WINDOWS:
            m = long_means.get(w, {}).get(symbol)
            if m is not None:
                per_window.append((w, m[0], m[1] >= math.ceil(w * LONG_MIN_COVERAGE)))

        for w, avg, enough in per_window:
            eligible = enough & fresh
            evaluated.update((EXCHANGE_IDS[a], EXCHANGE_IDS[b], symbol, w) for a, b in np.argwhere(eligible))
            deviation = np.round(current - avg, 4)                          # 與 Dashboard 相同：4 位小數判斷
            for a, b in np.argwhere(eligible & (deviation > STRONG_BUY_DEV) & profitable):
                i = last_idx[a, b]
                strong[(EXCHANGE_IDS[a], EXCHANGE_IDS[b], symbol, w)] = {
                    "data_time": pd.Timestamp(times[i]).to_pydatetime(),
                    "open_gap": round(float(current[a, b]), 4),
                    "avg_open_gap": round(float(avg[a, b]), 4),
                    "deviation": float(deviation[a, b]),
                    "base_spot_ask": float(sa[i, a]),
                    "target_contract_bid": float(cb[i, b]),
                    "points": int(count[a, b]),
                }
    return evaluated, strong


def check_capacity(combos):
    """查候選組合 (base, target, symbol) 兩邊的即時訂單簿。同一輪同一個交易所的同一邊只查一次。
    回傳 {combo: {"usd": 可套利金額, "qty": 幣量, "contract_usd": 放空合約金額, "round_trip": 獲利空間 %} 或 None}。
    獲利空間 = 最佳價的 Open Gap + Close Gap ≈ −(現貨買賣價差 + 合約買賣價差)，即平倉時要付出的價差成本。"""
    legs = {(base, "spot", sym) for base, _, sym in combos} | {(target, "contract", sym) for _, target, sym in combos}
    futures = {leg: _book_pool.submit(fetch_book, *leg) for leg in legs}
    done, _ = wait(futures.values(), timeout=BOOK_TIMEOUT)
    books = {}
    for leg, fut in futures.items():
        if fut in done and fut.exception() is None:
            books[leg] = fut.result()
        elif fut in done:
            log.warning(f"Order book {leg} failed: {fut.exception()}")
    result = {}
    for base, target, sym in combos:
        spot, contract = books.get((base, "spot", sym)), books.get((target, "contract", sym))
        if not spot or not contract or not spot[0] or not spot[1] or not contract[0] or not contract[1]:
            result[(base, target, sym)] = None
            continue
        usd, qty, contract_usd = arbitrage_capacity(spot[1], contract[0], MIN_OPEN_GAP)
        s_bid, s_ask, c_bid, c_ask = spot[0][0][0], spot[1][0][0], contract[0][0][0], contract[1][0][0]
        round_trip = (c_bid - s_ask) / s_ask * 100 + (s_bid - c_ask) / c_ask * 100
        result[(base, target, sym)] = {
            "usd": usd, "qty": qty, "contract_usd": contract_usd, "round_trip": round_trip,
            # 兩邊各自的買賣價差：任一邊太大（洗盤 / 套利陷阱）開倉就注定虧在價差上
            "spot_spread": (s_ask - s_bid) / s_bid * 100,
            "contract_spread": (c_ask - c_bid) / c_bid * 100,
        }
    return result


def entry_check(cap):
    """即時訂單簿的進場條件。回傳 None 表示通過，否則回傳拒絕原因（統計用）。"""
    if cap is None or cap["usd"] < MIN_CAPACITY_USD:
        return "rej_capacity"
    if cap["spot_spread"] > MAX_SPOT_SPREAD:
        return "rej_spot_spread"
    if cap["contract_spread"] > MAX_CONTRACT_SPREAD:
        return "rej_contract_spread"
    if cap["round_trip"] < MIN_ROUND_TRIP:
        return "rej_spread"
    return None


def record(cursor, key, s, cap):
    """寫入一筆強力買紀錄，回傳新紀錄的 Id；同一筆行情已記錄過則回傳 None。"""
    base, target, symbol, w = key
    try:
        cursor.execute(
            """
            INSERT INTO [dbo].[StrongBuySignals]
                ([DataTime], [Symbol], [BaseExchange], [TargetExchange], [OpenGap], [AvgOpenGap],
                 [Deviation], [BaseSpotAsk], [TargetContractBid], [WindowMinutes], [CapacityUsd], [CapacityQty],
                 [RoundTripPct], [SpotSpreadPct], [ContractSpreadPct])
            OUTPUT INSERTED.[Id]
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [s["data_time"], symbol, base, target, s["open_gap"], s["avg_open_gap"], s["deviation"],
             s["base_spot_ask"], s["target_contract_bid"], w,
             round(cap["usd"], 2), round(cap["qty"], 10), round(cap["round_trip"], 6),
             round(cap["spot_spread"], 6), round(cap["contract_spread"], 6)],
        )
        signal_id = int(cursor.fetchone()[0])
    except pyodbc.IntegrityError:
        return None   # 同一筆行情、同一區間已記錄過
    log.info(
        f"STRONG BUY [{window_label(w)}] {symbol} {base}->{target}: Open Gap {s['open_gap']:+.4f}% "
        f"avg {s['avg_open_gap']:+.4f}% dev {s['deviation']:+.4f}% capacity ${cap['usd']:,.0f} "
        f"round-trip {cap['round_trip']:+.4f}% spreads spot {cap['spot_spread']:.4f}% / contract {cap['contract_spread']:.4f}%"
    )
    send_telegram(
        f"🔥 強力買 {symbol}（{window_label(w)} 均值）\n"
        f"{EXCHANGES[base]['name']} 現貨買 → {EXCHANGES[target]['name']} 合約賣\n"
        f"Open Gap {s['open_gap']:+.4f}%（均值 {s['avg_open_gap']:+.4f}%，偏離 {s['deviation']:+.4f}%）\n"
        f"可套利金額 約 {cap['usd']:,.0f} USDT，獲利空間 {cap['round_trip']:+.4f}%\n"
        f"{s['data_time']:%Y-%m-%d %H:%M:%S}"
    )
    return signal_id


def _timed_check(combos):
    """背景執行查訂單簿，並回傳完成時間（判斷是否超過 MAX_CHECK_AGE）。"""
    return check_capacity(combos), time.time()


class BookCheckQueue:
    """候選訊號 → 查即時訂單簿的排隊管理。
    1) 以「組合」(base, target, symbol) 為單位：同一組合被多個均值區間觸發時只查一次，結果套用到所有區間
    2) 同時最多 MAX_INFLIGHT 個組合在查；有空位時依偏離大小（多區間取最大）優先補上，其餘下一輪重新排
    3) 送出後超過 MAX_CHECK_AGE 秒還沒查完（或查完時已超過）→ 丟棄，不用過時訊號開倉；仍是強力買的話下一輪以新行情重查
    """

    def __init__(self, executor, check_fn=_timed_check, max_inflight=None, max_age=None, recheck=None):
        self.executor, self.check_fn = executor, check_fn
        self.max_inflight = MAX_INFLIGHT if max_inflight is None else max_inflight
        self.max_age = MAX_CHECK_AGE if max_age is None else max_age
        self.recheck = RECHECK_SECONDS if recheck is None else recheck
        self.pending = {}    # 組合 -> (future, 送出時間, {(組合, 區間): 偵測當下的訊號})
        self.rejected = {}   # 組合 -> 下次可重查的時間（掛單不足 / 價差太大 / 查詢失敗）
        self.stats = {"expired": 0, "deferred": 0, "rej_capacity": 0, "rej_spot_spread": 0,
                      "rej_contract_spread": 0, "rej_spread": 0, "errors": 0}

    def collect(self, now):
        """回傳本輪查完、且可套利金額與獲利空間都達標的 [(組合, {key: 訊號}, 查詢結果)]。"""
        accepted = []
        for combo, (fut, submitted, sigs) in list(self.pending.items()):
            if not fut.done():
                if now - submitted > self.max_age:      # 超過時限仍在查 → 放棄
                    del self.pending[combo]
                    self.stats["expired"] += 1
                continue
            del self.pending[combo]
            if fut.exception() is not None:
                self.rejected[combo] = now + self.recheck
                self.stats["errors"] += 1
                continue
            results, finished = fut.result()
            if finished - submitted > self.max_age:     # 查完了但已超過時限 → 結果作廢
                self.stats["expired"] += 1
                continue
            cap = results.get(combo)
            reason = entry_check(cap)
            if reason is None:
                self.rejected.pop(combo, None)
                accepted.append((combo, sigs, cap))
            else:
                self.rejected[combo] = now + self.recheck
                self.stats[reason] += 1
        return accepted

    def submit(self, strong, in_strong, now):
        """把尚未記錄的強力買依組合分組，依偏離大小補滿 MAX_INFLIGHT 個空位。回傳本輪送出的組合。"""
        groups = {}
        for key, signal in strong.items():
            combo = key[:3]
            if key in in_strong or combo in self.pending or self.rejected.get(combo, 0) > now:
                continue
            groups.setdefault(combo, {})[key] = signal
        slots = self.max_inflight - len(self.pending)
        if not groups or slots <= 0:
            self.stats["deferred"] += len(groups)
            return []
        ranked = sorted(groups, key=lambda c: max(s["deviation"] for s in groups[c].values()), reverse=True)
        chosen, self.stats["deferred"] = ranked[:slots], self.stats["deferred"] + max(0, len(ranked) - slots)
        fut = self.executor.submit(self.check_fn, chosen)
        for combo in chosen:
            self.pending[combo] = (fut, now, groups[combo])
        return chosen

    def forget(self, evaluated, strong):
        """本輪有評估、但已不是強力買的組合 → 清掉重查等待，下次進入強力買時立刻可查。"""
        strong_combos = {k[:3] for k in strong}
        evaluated_combos = {k[:3] for k in evaluated}
        for combo in [c for c in self.rejected if c in evaluated_combos and c not in strong_combos]:
            del self.rejected[combo]

    def take_stats(self):
        stats, self.stats = self.stats, {k: 0 for k in self.stats}
        return stats


def main():
    log.info(
        f"Signal detector started: {len(EXCHANGE_IDS)} exchanges, windows={','.join(window_label(w) for w in WINDOWS)}, "
        f"strong buy dev>{STRONG_BUY_DEV}% and open gap>{MIN_OPEN_GAP}% and capacity>=${MIN_CAPACITY_USD:,.0f} "
        f"and round-trip>={MIN_ROUND_TRIP}% and spot spread<={MAX_SPOT_SPREAD}% and contract spread<={MAX_CONTRACT_SPREAD}%, "
        f"paper trades follow {window_label(PAPER_WINDOW)} signals"
    )
    threading.Thread(target=heartbeat_server, daemon=True).start()
    preload_specs(log)   # 合約規格（每張幾顆幣）背景預載，查訂單簿時就不用等下載

    window = MarketWindow()
    history = MinuteHistory()
    history.start_backfill()
    in_strong = set()          # 已記錄、仍處於強力買的 (組合, 區間)；只有「新進入」時才寫入
    books = BookCheckQueue(_capacity_runner)   # 候選 → 查即時訂單簿（組合去重、偏離優先、5 秒過期）
    trader = PaperTrader(_close_runner)        # 套利模擬交易（平倉用自己的工作線）
    conn = cursor = None
    cycles, recorded, spent = 0, 0, 0.0

    while True:
        started = time.time()
        try:
            if conn is None:
                conn = get_conn()
                cursor = conn.cursor()
                log.info("MSSQL connected")
            window.refresh(cursor)
            history.update(window)
            evaluated, strong = detect(window, history)

            # 1) 5 秒內查完訂單簿、且可套利金額與獲利空間達標的組合 → 記錄該組合所有觸發的區間
            now = time.time()
            for combo, sigs, cap in books.collect(now):
                for key, signal in sigs.items():
                    signal_id = record(cursor, key, signal, cap)
                    if signal_id is not None:
                        recorded += 1
                        if key[3] == PAPER_WINDOW:
                            # 模擬交易：以同一份訂單簿逐檔成交結果開倉（用盡可套利金額）
                            trader.open(cursor, signal_id, combo, signal,
                                        (cap["usd"], cap["qty"], cap["contract_usd"]))
                    in_strong.add(key)

            # 2) 新候選 → 依偏離大小補滿同時查詢的空位（背景執行，不卡住每秒的偵測）
            books.submit(strong, in_strong, now)

            # 本輪有評估、但已不是強力買的 (組合, 區間) → 離開狀態（下次再進入會重新檢查、記錄）
            # 本輪沒評估到的（資料暫停、樣本不足）保留原狀態，恢復後不會被重複記錄
            in_strong -= evaluated - strong.keys()
            books.forget(evaluated, strong)

            # 3) 模擬交易：持倉估值、判斷平倉、完成平倉
            if not trader.loaded:
                trader.load_open(cursor)
            trader.step(cursor, window.latest_quotes(), window.latest)
        except Exception as exc:
            log.error(f"Detect cycle failed: {exc}")
            conn = cursor = None
            time.sleep(5)
            continue

        cycles += 1
        spent += time.time() - started
        if cycles % 60 == 0:
            by_window = {w: sum(1 for k in evaluated if k[3] == w) for w in WINDOWS}
            st = books.take_stats()
            log.info(
                f"Status: evaluated {' '.join(f'{window_label(w)}={n}' for w, n in by_window.items())}"
                f"{'' if history.ready else ' (long windows backfilling)'}; "
                f"{len(in_strong)} recorded & still strong, {len(books.rejected)} combos waiting recheck, "
                f"{len(books.pending)}/{books.max_inflight} combos checking books; "
                f"last 60 cycles: {recorded} recorded, rejected {st['rej_capacity']} capacity / "
                f"{st['rej_spot_spread']} spot spread / {st['rej_contract_spread']} contract spread / {st['rej_spread']} round-trip, "
                f"{st['expired']} expired (>{books.max_age:g}s), {st['deferred']} deferred (queue full), {st['errors']} errors; "
                f"avg cycle {spent / 60 * 1000:.0f} ms; paper: {len(trader.positions)} open, {len(trader.closing)} closing"
            )
            recorded, spent = 0, 0.0
        time.sleep(max(0.0, POLL_INTERVAL - (time.time() - started)))


if __name__ == "__main__":
    main()
