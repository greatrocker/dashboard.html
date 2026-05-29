# -*- coding: utf-8 -*-
import json
import logging
import os
import queue
import socket
import threading
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler

import pandas as pd
import pyodbc
import requests
import websocket

from config import (
    CURRENT_EXCHANGE,
    EXCHANGE,
    HEARTBEAT_PORT,
    LOG_DIR,
    MSSQL_DATABASE,
    MSSQL_PASSWORD,
    MSSQL_SERVER,
    MSSQL_USER,
    SYMBOLS,
    TELEGRAM_CHAT_ID,
    TELEGRAM_TOKEN,
)


os.makedirs(LOG_DIR, exist_ok=True)
log_file = f"{LOG_DIR}/{EXCHANGE}_ticker.log"
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

file_handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
file_handler.setFormatter(formatter)
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

log = logging.getLogger("binance_ticker")
log.setLevel(logging.INFO)
log.addHandler(file_handler)
log.addHandler(console_handler)


latest_prices = {
    symbol: {
        "Spot_bids": None,
        "Spot_asks": None,
        "Contract_bids": None,
        "Contract_asks": None,
    }
    for symbol in SYMBOLS
}
data_queue = queue.Queue()


def send_telegram(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)
    except Exception as exc:
        log.warning(f"Telegram failed: {exc}")


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


def subscribe_topics(ws, market_type):
    params = [f"{symbol.lower()}@bookTicker" for symbol in SYMBOLS]
    ws.send(json.dumps({"method": "SUBSCRIBE", "params": params, "id": 1}))
    log.info(f"{market_type} subscribed: {len(params)} symbols")


def on_message(_, message, market_type):
    try:
        msg = json.loads(message)
    except json.JSONDecodeError:
        return

    if msg.get("result") is None and msg.get("id") is not None:
        log.info(f"{market_type} subscription acknowledged: {msg}")
        return

    symbol = msg.get("s")
    bids = msg.get("b")
    asks = msg.get("a")
    if symbol not in latest_prices or bids is None or asks is None:
        return

    # 只更新快取，不處理邏輯，確保 WS 執行緒極速運行
    latest_prices[symbol][f"{market_type}_bids"] = float(bids)
    latest_prices[symbol][f"{market_type}_asks"] = float(asks)


def run_ws(ws_url, market_type):
    while True:
        try:
            ws = websocket.WebSocketApp(
                ws_url,
                on_open=lambda current_ws: subscribe_topics(current_ws, market_type),
                on_message=lambda current_ws, msg: on_message(current_ws, msg, market_type),
                on_error=lambda current_ws, err: log.error(f"{market_type} WS Error: {err}"),
                on_close=lambda current_ws, status_code, close_msg: log.warning(
                    f"{market_type} WS closed: {status_code} {close_msg}"
                ),
            )
            ws.run_forever(ping_interval=20, ping_timeout=10)
        except Exception as exc:
            log.error(f"{market_type} WS Exception: {exc}")
        time.sleep(5)


def snapshot_loop():
    """
    仿造 Bybit 邏輯：每秒固定掃描一次快照並放入隊列
    """
    while True:
        now = datetime.now()
        time_str = now.strftime("%Y-%m-%d %H:%M:%S")
        rows = []
        ready_count = 0
        for symbol, prices in latest_prices.items():
            # 檢查是否 Spot 和 Contract 都有資料
            if all(v is not None for v in prices.values()):
                rows.append({"Time": time_str, "symbol": symbol, **prices})
                ready_count += 1
            else:
                # 調試用：如果是 BTC 但沒資料，印出缺少什麼
                if "BTCUSDT" in symbol:
                    missing = [k for k, v in prices.items() if v is None]
                    log.debug(f"⏳ {symbol} waiting for: {missing}")

        if rows:
            data_queue.put(pd.DataFrame(rows))
            log.info(f"📊 Snapshot: {ready_count}/{len(SYMBOLS)} symbols ready")
        else:
            log.info(f"⏳ Waiting for data... {ready_count}/{len(SYMBOLS)} symbols ready")

        time.sleep(1)


def upload_sql():
    conn = None
    cursor = None
    while True:
        if conn is None:
            try:
                conn = pyodbc.connect(
                    (
                        "DRIVER={ODBC Driver 18 for SQL Server};"
                        f"SERVER={MSSQL_SERVER};"
                        f"DATABASE={MSSQL_DATABASE};"
                        f"UID={MSSQL_USER};"
                        f"PWD={MSSQL_PASSWORD};"
                        "Encrypt=no;TrustServerCertificate=yes;LoginTimeout=30;"
                    ),
                    autocommit=True,
                )
                cursor = conn.cursor()
                log.info("💾 MSSQL connected")
            except Exception as exc:
                log.error(f"❌ MSSQL connect failed: {exc}")
                time.sleep(10)
                continue

        try:
            # 從隊列獲取 DataFrame
            df = data_queue.get(timeout=5)
            for _, row in df.iterrows():
                cursor.execute(
                    f"EXEC {CURRENT_EXCHANGE['sp_name']} ?, ?, ?, ?, ?, ?",
                    (
                        row["Time"],
                        row["symbol"],
                        row["Spot_bids"],
                        row["Spot_asks"],
                        row["Contract_bids"],
                        row["Contract_asks"],
                    ),
                )
            log.info(f"✅ Written to MSSQL: {len(df)} rows")

            if data_queue.qsize() > 50:
                log.warning(f"⚠️ Database queue pressure: {data_queue.qsize()} rows")
        except queue.Empty:
            pass
        except Exception as exc:
            log.error(f"❌ MSSQL write failed: {exc}")
            conn = None
            cursor = None
            time.sleep(5)


if __name__ == "__main__":
    if EXCHANGE != "binance":
        raise ValueError("binance_ticker.py requires EXCHANGE=binance")

    log.info(f"🚀 {CURRENT_EXCHANGE['display_name']} started (Snapshot mode)")
    threading.Thread(target=heartbeat_server, daemon=True).start()

    # 啟動 WebSocket 連線執行緒
    threading.Thread(target=run_ws, args=(CURRENT_EXCHANGE["ws_spot_url"], "Spot"), daemon=True).start()
    threading.Thread(target=run_ws, args=(CURRENT_EXCHANGE["ws_contract_url"], "Contract"), daemon=True).start()

    # 啟動快照執行緒 (核心優化)
    threading.Thread(target=snapshot_loop, daemon=True).start()

    # 主執行緒負責資料庫寫入
    upload_sql()
