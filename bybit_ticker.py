# bybit_ticker.py
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

# ==============================
# Logger 設定
# ==============================
os.makedirs(LOG_DIR, exist_ok=True)
log_file = f"{LOG_DIR}/{EXCHANGE}_ticker.log"

file_handler = RotatingFileHandler(
    log_file,
    maxBytes=10*1024*1024,
    backupCount=5,
    encoding='utf-8'
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))

logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
log = logging.getLogger(__name__)

# ==============================
# 資料快取與佇列
# ==============================
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
        log.warning(f"Telegram send failed: {e}")

def heartbeat_server():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", HEARTBEAT_PORT))
    srv.listen(5)
    log.info(f"TCP heartbeat server started on port {HEARTBEAT_PORT}")
    while True:
        try:
            conn, addr = srv.accept()
            conn.close()
        except Exception: pass

def start_heartbeat(ws):
    def run():
        while getattr(ws, 'sock', None) and ws.sock.connected:
            try:
                ws.send(json.dumps({"op": "ping"}))
                time.sleep(20)
            except: break
    threading.Thread(target=run, daemon=True).start()

# ==============================
# Spot WebSocket
# ==============================
def on_open_spot(ws):
    start_heartbeat(ws)
    if EXCHANGE == "bybit":
        args = [CURRENT_EXCHANGE["orderbook_topic_template"].format(symbol=s) for s in SYMBOLS]
        ws.send(json.dumps({"op": "subscribe", "args": args}))
    log.info("Spot WebSocket opened & subscribed")

def on_message_spot(ws, message):
    msg = json.loads(message)
    if msg.get("ret_msg") == "pong" or msg.get("op") == "pong": return
    if "topic" in msg and "orderbook" in msg["topic"]:
        symbol = msg["topic"].split(".")[-1]
        if symbol in latest_prices:
            data = msg["data"]
            b = data.get("b", []); a = data.get("a", [])
            if b: latest_prices[symbol]["Spot_bids"] = float(b[0][0])
            if a: latest_prices[symbol]["Spot_asks"] = float(a[0][0])

def spot_ws():
    while True:
        try:
            ws = websocket.WebSocketApp(
                CURRENT_EXCHANGE["ws_spot_url"],
                on_open=on_open_spot, on_message=on_message_spot,
                on_error=lambda ws, e: log.error(f"Spot WS Error: {e}"),
                on_close=lambda ws, c, m: log.warning(f"Spot WS Closed: {c} {m}")
            )
            ws.run_forever()
        except Exception as e: log.error(f"Spot WS Exception: {e}")
        time.sleep(5)

# ==============================
# Contract WebSocket
# ==============================
def on_open_contract(ws):
    start_heartbeat(ws)
    if EXCHANGE == "bybit":
        args = [CURRENT_EXCHANGE["orderbook_topic_template"].format(symbol=s) for s in SYMBOLS]
        ws.send(json.dumps({"op": "subscribe", "args": args}))
    log.info("Contract WebSocket opened & subscribed")

def on_message_contract(ws, message):
    msg = json.loads(message)
    if msg.get("ret_msg") == "pong" or msg.get("op") == "pong": return
    if "topic" in msg and "orderbook" in msg["topic"]:
        symbol = msg["topic"].split(".")[-1]
        if symbol in latest_prices:
            data = msg["data"]
            b = data.get("b", []); a = data.get("a", [])
            if b: latest_prices[symbol]["Contract_bids"] = float(b[0][0])
            if a: latest_prices[symbol]["Contract_asks"] = float(a[0][0])

def contract_ws():
    while True:
        try:
            ws = websocket.WebSocketApp(
                CURRENT_EXCHANGE["ws_contract_url"],
                on_open=on_open_contract, on_message=on_message_contract,
                on_error=lambda ws, e: log.error(f"Contract WS Error: {e}"),
                on_close=lambda ws, c, m: log.warning(f"Contract WS Closed: {c} {m}")
            )
            ws.run_forever()
        except Exception as e: log.error(f"Contract WS Exception: {e}")
        time.sleep(5)

def snapshot_loop():
    while True:
        now = datetime.now()
        Time = now.strftime("%Y-%m-%d %H:%M:%S")
        rows = []
        for symbol, prices in latest_prices.items():
            if all(v is not None for v in prices.values()):
                rows.append({"Time": Time, "symbol": symbol, **prices})
        if rows:
            data_queue.put(pd.DataFrame(rows))
            log.info(f"Snapshot queued: {len(rows)} symbols")
        time.sleep(1)

def upload_sql():
    conn = None
    while True:
        if conn is None:
            try:
                conn = pyodbc.connect(f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={MSSQL_SERVER};DATABASE={MSSQL_DATABASE};UID={MSSQL_USER};PWD={MSSQL_PASSWORD};Encrypt=no;TrustServerCertificate=yes;LoginTimeout=30;", autocommit=True)
                cursor = conn.cursor()
                log.info("MSSQL connected")
            except Exception as e:
                log.error(f"MSSQL connect failed: {e}"); time.sleep(10); continue
        try:
            df = data_queue.get(timeout=5)
            for _, row in df.iterrows():
                cursor.execute(f"EXEC {CURRENT_EXCHANGE['sp_name']} ?, ?, ?, ?, ?, ?", (row['Time'], row['symbol'], row['Spot_bids'], row['Spot_asks'], row['Contract_bids'], row['Contract_asks']))
            log.info(f"Written to MSSQL: {len(df)} rows")
        except queue.Empty: pass
        except Exception as e:
            log.error(f"MSSQL write failed: {e}"); conn = None; time.sleep(5)

if __name__ == '__main__':
    log.info(f"{CURRENT_EXCHANGE['display_name']} ticker started")
    threading.Thread(target=heartbeat_server, daemon=True).start()
    threading.Thread(target=spot_ws,          daemon=True).start()
    threading.Thread(target=contract_ws,      daemon=True).start()
    threading.Thread(target=snapshot_loop,    daemon=True).start()
    threading.Thread(target=upload_sql,       daemon=True).start()
    while True:
        log.info("Main heartbeat OK")
        time.sleep(60)
