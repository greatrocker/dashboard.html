# -*- coding: utf-8 -*-
"""REST 輪詢型 Ticker 共用骨架。

各交易所的 <name>_ticker.py 只需要提供兩個函式：
    fetch_spot(symbols)     -> {"BTCUSDT": (bid, ask), ...}
    fetch_contract(symbols) -> {"BTCUSDT": (bid, ask), ...}
再呼叫 run("<name>", fetch_spot, fetch_contract)。
Log、Heartbeat、快照、寫入 MSSQL（EXEC sp_name）都由這裡處理。
"""
import logging
import os
import queue
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from logging.handlers import RotatingFileHandler

import pandas as pd
import pyodbc
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


REQUEST_TIMEOUT = 10

# 共用連線（keep-alive）：避免每次輪詢都重新 DNS 查詢 + TLS 握手；
# 短暫 DNS / 連線錯誤由 urllib3 自動重試
http = requests.Session()
http.headers["User-Agent"] = "Mozilla/5.0 (exchange-monitor)"
http.mount("https://", HTTPAdapter(pool_maxsize=16, max_retries=Retry(
    total=4, connect=3, read=1, status=2, backoff_factor=0.5,
    status_forcelist=(429, 500, 502, 503, 504), allowed_methods=frozenset({"GET"}),
)))


def get_json(url, params=None):
    response = http.get(url, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def to_float(value):
    """交易所用 0 / "" / None 表示沒有掛單，一律視為缺值。"""
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def base_of(symbol: str) -> str:
    """BTCUSDT -> BTC"""
    return symbol[:-4] if symbol.endswith("USDT") else symbol


def collect(items, native_to_symbol, key, bid_key, ask_key):
    """從 list[dict] 取出指定幣種的 (bid, ask)；native_to_symbol: 交易所代號 -> BTCUSDT。"""
    result = {}
    for item in items:
        symbol = native_to_symbol.get(item.get(key))
        if symbol is None:
            continue
        bid, ask = to_float(item.get(bid_key)), to_float(item.get(ask_key))
        if bid and ask:
            result[symbol] = (bid, ask)
    return result


_unsupported = set()
_per_symbol_pool = ThreadPoolExecutor(max_workers=8)


def fetch_each(symbols, fetch_one):
    """給只有「單一幣種」查詢 API 的交易所用：平行查詢，回 4xx 的幣種之後不再查。"""
    def task(symbol):
        if symbol in _unsupported:
            return symbol, None
        try:
            return symbol, fetch_one(symbol)
        except requests.HTTPError as exc:
            if exc.response is not None and 400 <= exc.response.status_code < 500:
                _unsupported.add(symbol)
                return symbol, None
            raise

    return {s: v for s, v in _per_symbol_pool.map(task, symbols) if v}


def run(exchange_id, fetch_spot, fetch_contract, poll_interval=1):
    from config import (
        CURRENT_EXCHANGE, EXCHANGE, HEARTBEAT_PORT, LOG_DIR,
        MSSQL_DATABASE, MSSQL_PASSWORD, MSSQL_SERVER, MSSQL_USER, SYMBOLS,
    )

    if EXCHANGE != exchange_id:
        raise ValueError(f"{exchange_id}_ticker.py requires EXCHANGE={exchange_id}")

    os.makedirs(LOG_DIR, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    file_handler = RotatingFileHandler(
        f"{LOG_DIR}/{exchange_id}_ticker.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    log = logging.getLogger(f"{exchange_id}_ticker")
    log.setLevel(logging.INFO)
    log.addHandler(file_handler)
    log.addHandler(console_handler)

    name = CURRENT_EXCHANGE["name"]
    latest_prices = {
        symbol: {"Spot_bids": None, "Spot_asks": None, "Contract_bids": None, "Contract_asks": None}
        for symbol in SYMBOLS
    }
    data_queue = queue.Queue()
    pool = ThreadPoolExecutor(max_workers=2)

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

    def snapshot_loop():
        while True:
            try:
                spot_future = pool.submit(fetch_spot, SYMBOLS)
                contract_future = pool.submit(fetch_contract, SYMBOLS)
                spot, contract = spot_future.result(), contract_future.result()
            except Exception as exc:
                log.error(f"{name} REST fetch failed: {exc}")
                time.sleep(5)
                continue

            # 這一輪沒拿到報價的幣種清成 None（不寫入），避免舊價格被當成新資料一直寫進 DB
            for symbol, prices in latest_prices.items():
                prices["Spot_bids"], prices["Spot_asks"] = spot.get(symbol, (None, None))
                prices["Contract_bids"], prices["Contract_asks"] = contract.get(symbol, (None, None))

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rows = [
                {"Time": now, "symbol": symbol, **prices}
                for symbol, prices in latest_prices.items()
                if all(value is not None for value in prices.values())
            ]
            if rows:
                data_queue.put(pd.DataFrame(rows))
                log.info(f"Snapshot: {len(rows)}/{len(SYMBOLS)} ready (spot={len(spot)}, contract={len(contract)})")
            else:
                log.info(f"Waiting... 0/{len(SYMBOLS)} ready (spot={len(spot)}, contract={len(contract)})")

            time.sleep(poll_interval)

    def upload_sql():
        conn = None
        cursor = None
        while True:
            if conn is None:
                try:
                    conn = pyodbc.connect(
                        "DRIVER={ODBC Driver 18 for SQL Server};"
                        f"SERVER={MSSQL_SERVER};DATABASE={MSSQL_DATABASE};"
                        f"UID={MSSQL_USER};PWD={MSSQL_PASSWORD};"
                        "Encrypt=no;TrustServerCertificate=yes;LoginTimeout=30;",
                        autocommit=True,
                    )
                    cursor = conn.cursor()
                    log.info("MSSQL connected")
                except Exception as exc:
                    log.error(f"MSSQL connect failed: {exc}")
                    time.sleep(10)
                    continue

            try:
                df = data_queue.get(timeout=5)
                for _, row in df.iterrows():
                    cursor.execute(
                        f"EXEC {CURRENT_EXCHANGE['sp_name']} ?, ?, ?, ?, ?, ?",
                        (row["Time"], row["symbol"], row["Spot_bids"], row["Spot_asks"],
                         row["Contract_bids"], row["Contract_asks"]),
                    )
                log.info(f"Written to MSSQL: {len(df)} rows")
            except queue.Empty:
                pass
            except Exception as exc:
                log.error(f"MSSQL write failed: {exc}")
                conn = None
                cursor = None
                time.sleep(5)

    log.info(f"{CURRENT_EXCHANGE['display_name']} started (REST snapshot mode, every {poll_interval}s)")
    threading.Thread(target=heartbeat_server, daemon=True).start()
    threading.Thread(target=snapshot_loop, daemon=True).start()
    upload_sql()
