# -*- coding: utf-8 -*-
import websocket
import json
import threading
import socket
import queue
import time
import logging
from logging.handlers import RotatingFileHandler
import os
import requests
import pandas as pd
from datetime import datetime
import pyodbc
from config import (
    EXCHANGE, CURRENT_EXCHANGE, SYMBOLS,
    MSSQL_SERVER, MSSQL_DATABASE, MSSQL_USER, MSSQL_PASSWORD,
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, HEARTBEAT_PORT, LOG_DIR
)

# Logger 設定
os.makedirs(LOG_DIR, exist_ok=True)
log_file = f"{LOG_DIR}/{EXCHANGE}_ticker.log"
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
file_handler.setFormatter(formatter)
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

log = logging.getLogger("bybit_ticker")
log.setLevel(logging.DEBUG)
log.addHandler(file_handler)
log.addHandler(console_handler)

latest_prices = {
    symbol: {
        "Spot_bids": None, "Spot_asks": None,
        "Contract_bids": None, "Contract_asks": None
    }
    for symbol in SYMBOLS
}
data_queue = queue.Queue()

def send_telegram(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)
    except Exception as e:
        log.warning(f"Telegram failed: {e}")

def heartbeat_server():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", HEARTBEAT_PORT))
    srv.listen(5)
    log.info(f"Heartbeat server on port {HEARTBEAT_PORT}")
    while True:
        try:
            conn, addr = srv.accept()
            conn.close()
        except Exception: pass

def bybit_ping(ws):
    while True:
        time.sleep(20)
        try:
            ws.send(json.dumps({"op": "ping"}))
        except Exception: break

def on_message(ws, message, market_type):
    try:
        msg = json.loads(message)
    except: return

    if msg.get("ret_msg") == "pong" or msg.get("op") == "pong":
        return
    
    if "success" in msg:
        log.info(f"✅ {market_type} Subscribed: {msg}")
        return

    if "topic" in msg and "orderbook" in msg["topic"]:
        topic = msg["topic"]
        symbol = topic.split(".")[-1]
        if symbol in latest_prices:
            data = msg.get("data", {})
            b = data.get("b", [])
            a = data.get("a", [])
            if b:
                latest_prices[symbol][f"{market_type}_bids"] = float(b[0][0])
            if a:
                latest_prices[symbol][f"{market_type}_asks"] = float(a[0][0])

def subscribe_topics(ws):
    time.sleep(1)
    # 分批訂閱，每批最多 10 個
    for i in range(0, len(SYMBOLS), 10):
        chunk = SYMBOLS[i:i+10]
        args = [CURRENT_EXCHANGE["orderbook_topic_template"].format(symbol=s) for s in chunk]
        ws.send(json.dumps({"op": "subscribe", "args": args}))
        log.info(f"📡 Sent subscription chunk: {chunk}")

def spot_ws():
    while True:
        try:
            ws = websocket.WebSocketApp(
                CURRENT_EXCHANGE["ws_spot_url"],
                on_open=lambda ws: threading.Thread(target=subscribe_topics, args=(ws,), daemon=True).start(),
                on_message=lambda ws, msg: on_message(ws, msg, "Spot"),
                on_error=lambda ws, e: log.error(f"Spot WS Error: {e}")
            )
            threading.Thread(target=bybit_ping, args=(ws,), daemon=True).start()
            ws.run_forever()
        except Exception as e: log.error(f"Spot WS Exception: {e}")
        time.sleep(5)

def contract_ws():
    while True:
        try:
            ws = websocket.WebSocketApp(
                CURRENT_EXCHANGE["ws_contract_url"],
                on_open=lambda ws: threading.Thread(target=subscribe_topics, args=(ws,), daemon=True).start(),
                on_message=lambda ws, msg: on_message(ws, msg, "Contract"),
                on_error=lambda ws, e: log.error(f"Contract WS Error: {e}")
            )
            threading.Thread(target=bybit_ping, args=(ws,), daemon=True).start()
            ws.run_forever()
        except Exception as e: log.error(f"Contract WS Exception: {e}")
        time.sleep(5)

def snapshot_loop():
    while True:
        now = datetime.now()
        Time = now.strftime("%Y-%m-%d %H:%M:%S")
        rows = []
        ready_count = 0
        for symbol, prices in latest_prices.items():
            if all(v is not None for v in prices.values()):
                rows.append({"Time": Time, "symbol": symbol, **prices})
                ready_count += 1
            else:
                if "BTCUSDT" in symbol:
                    missing = [k for k, v in prices.items() if v is None]
                    log.debug(f"⏳ {symbol} missing: {missing}")
        
        if rows:
            data_queue.put(pd.DataFrame(rows))
            log.info(f"🚀 Snapshot: {ready_count}/{len(SYMBOLS)} symbols ready")
        else:
            log.info(f"⏳ Waiting... {ready_count}/{len(SYMBOLS)} symbols ready")
        
        time.sleep(1)

def upload_sql():
    conn = None
    while True:
        if conn is None:
            try:
                conn = pyodbc.connect(
                    f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={MSSQL_SERVER};DATABASE={MSSQL_DATABASE};UID={MSSQL_USER};PWD={MSSQL_PASSWORD};Encrypt=no;TrustServerCertificate=yes;LoginTimeout=30;",
                    autocommit=True
                )
                cursor = conn.cursor()
                log.info("✅ MSSQL connected")
            except Exception as e:
                log.error(f"❌ MSSQL connect failed: {e}")
                time.sleep(10)
                continue
        try:
            df = data_queue.get(timeout=5)
            for _, row in df.iterrows():
                cursor.execute(f"EXEC {CURRENT_EXCHANGE['sp_name']} ?, ?, ?, ?, ?, ?", (row['Time'], row['symbol'], row['Spot_bids'], row['Spot_asks'], row['Contract_bids'], row['Contract_asks']))
            log.info(f"💾 Written to MSSQL: {len(df)} rows")
        except queue.Empty: pass
        except Exception as e:
            log.error(f"❌ MSSQL write failed: {e}")
            conn = None
            time.sleep(5)

if __name__ == '__main__':
    log.info(f"🚀 {CURRENT_EXCHANGE['display_name']} started")
    threading.Thread(target=heartbeat_server, daemon=True).start()
    threading.Thread(target=spot_ws,          daemon=True).start()
    threading.Thread(target=contract_ws,      daemon=True).start()
    threading.Thread(target=snapshot_loop,    daemon=True).start()
    upload_sql()
