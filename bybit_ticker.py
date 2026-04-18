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

# logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.handlers.clear()
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)
log = logging.getLogger(__name__)

# ==============================
# 資料快取與佇列
# ==============================
latest_prices = {
    symbol: {
        "Spot_bids": None, "Spot_asks": None,
        "Contract_bids": None, "Contract_asks": None
    }
    for symbol in ['BTCUSDT','ETHUSDT']
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

def bybit_ping(ws):
    """每 20 秒發送 Bybit 格式 ping"""
    while True:
        time.sleep(20)
        try:
            ws.send(json.dumps({"op": "ping"}))
            log.info("💓 Ping sent to Bybit")
        except Exception as e:
            log.warning(f"Ping failed: {e}")
            break

# ==============================
# Spot WebSocket
# ==============================
def on_open_spot(ws):
    threading.Thread(target=bybit_ping, args=(ws,), daemon=True).start()
    if EXCHANGE == "bybit":
        args = [CURRENT_EXCHANGE["orderbook_topic_template"].format(symbol=s) for s in SYMBOLS]
        ws.send(json.dumps({"op": "subscribe", "args": args}))
    log.info("🟢 Spot WebSocket opened & subscribed")

def on_message_spot(ws, message):
    msg = json.loads(message)
    if msg.get("ret_msg") == "pong" or msg.get("op") == "pong":
        log.info("🏓 Spot pong received")
        return
    if "topic" in msg and "orderbook" in msg["topic"]:
        symbol = msg["topic"].split(".")[-1]
        if symbol in latest_prices:
            data = msg["data"]
            b = data.get("b", [])
            a = data.get("a", [])
            if b:
                latest_prices[symbol]["Spot_bids"] = float(b[0][0])
            if a:
                latest_prices[symbol]["Spot_asks"] = float(a[0][0])
            # log.info(f"📈 Spot {symbol} bid={latest_prices[symbol]['Spot_bids']} ask={latest_prices[symbol]['Spot_asks']}")

def spot_ws():
    while True:
        try:
            ws = websocket.WebSocketApp(
                CURRENT_EXCHANGE["ws_spot_url"],
                on_open=on_open_spot,
                on_message=on_message_spot,
                on_error=lambda ws, e: log.error(f"❌ Spot WS Error: {e}"),
                on_close=lambda ws, c, m: log.warning(f"⚠️ Spot WS Closed: {c} {m}")
            )
            ws.run_forever()
        except Exception as e:
            log.error(f"Spot WS Exception: {e}")
        time.sleep(5)

# ==============================
# Contract WebSocket
# ==============================
def on_open_contract(ws):
    threading.Thread(target=bybit_ping, args=(ws,), daemon=True).start()
    if EXCHANGE == "bybit":
        args = [CURRENT_EXCHANGE["orderbook_topic_template"].format(symbol=s) for s in SYMBOLS]
        ws.send(json.dumps({"op": "subscribe", "args": args}))
    log.info("🟢 Contract WebSocket opened & subscribed")

def on_message_contract(ws, message):
    msg = json.loads(message)
    if msg.get("ret_msg") == "pong" or msg.get("op") == "pong":
        log.info("🏓 Contract pong received")
        return
    if "topic" in msg and "orderbook" in msg["topic"]:
        symbol = msg["topic"].split(".")[-1]
        if symbol in latest_prices:
            data = msg["data"]
            b = data.get("b", [])
            a = data.get("a", [])
            if b:
                latest_prices[symbol]["Contract_bids"] = float(b[0][0])
            if a:
                latest_prices[symbol]["Contract_asks"] = float(a[0][0])
            # log.info(f"📉 Contract {symbol} bid={latest_prices[symbol]['Contract_bids']} ask={latest_prices[symbol]['Contract_asks']}")

def contract_ws():
    while True:
        try:
            ws = websocket.WebSocketApp(
                CURRENT_EXCHANGE["ws_contract_url"],
                on_open=on_open_contract,
                on_message=on_message_contract,
                on_error=lambda ws, e: log.error(f"❌ Contract WS Error: {e}"),
                on_close=lambda ws, c, m: log.warning(f"⚠️ Contract WS Closed: {c} {m}")
            )
            ws.run_forever()
        except Exception as e:
            log.error(f"Contract WS Exception: {e}")
        time.sleep(5)

# ==============================
# Snapshot 每秒推入 queue
# ==============================
def snapshot_loop():
    while True:
        now = datetime.now()
        Time = now.strftime("%Y-%m-%d %H:%M:%S")
        rows = []
        for symbol, prices in latest_prices.items():
            if all(v is not None for v in prices.values()):
                rows.append({"Time": Time, "symbol": symbol, **prices})
            else:
                missing = [k for k, v in prices.items() if v is None]
                log.debug(f"⏳ {symbol} 尚未就緒，缺少: {missing}")
        if rows:
            data_queue.put(pd.DataFrame(rows))
            log.info(f"📦 Snapshot queued: {len(rows)}/{len(SYMBOLS)} symbols")
        else:
            log.info(f"⏳ 等待資料就緒，目前 0/{len(SYMBOLS)} symbols 有資料")
        time.sleep(1)

# ==============================
# MSSQL 上傳
# ==============================
def upload_sql():
    conn = None
    cursor = None
    while True:
        if conn is None:
            try:
                conn = pyodbc.connect(
                    f"DRIVER={{ODBC Driver 18 for SQL Server}};"
                    f"SERVER={MSSQL_SERVER};"
                    f"DATABASE={MSSQL_DATABASE};"
                    f"UID={MSSQL_USER};"
                    f"PWD={MSSQL_PASSWORD};"
                    f"Encrypt=no;"
                    f"TrustServerCertificate=yes;"
                    f"LoginTimeout=30;",
                    autocommit=True
                )
                cursor = conn.cursor()
                log.info("✅ MSSQL connected")
                send_telegram(f"✅ {CURRENT_EXCHANGE['display_name']}：MSSQL 連線成功，服務啟動")
            except Exception as e:
                log.error(f"❌ MSSQL connect failed: {e}")
                send_telegram(f"❌ MSSQL 連線失敗：{e}")
                time.sleep(10)
                continue
        try:
            df = data_queue.get(timeout=5)
            for _, row in df.iterrows():
                cursor.execute(
                    f"EXEC {CURRENT_EXCHANGE['sp_name']} ?, ?, ?, ?, ?, ?",
                    (row['Time'], row['symbol'], row['Spot_bids'], row['Spot_asks'], row['Contract_bids'], row['Contract_asks'])
                )
            log.info(f"📤 Written to MSSQL: {len(df)} rows")
        except queue.Empty:
            pass
        except Exception as e:
            log.error(f"❌ MSSQL write failed: {e}")
            send_telegram(f"❌ MSSQL 寫入失敗：{e}")
            try:
                conn.close()
            except Exception:
                pass
            conn = None
            cursor = None
            time.sleep(5)

if __name__ == '__main__':
    log.info(f"🚀 {CURRENT_EXCHANGE['display_name']} ticker started")
    send_telegram(f"🚀 {CURRENT_EXCHANGE['display_name']} 容器已啟動")
    threading.Thread(target=heartbeat_server, daemon=True).start()
    threading.Thread(target=spot_ws,          daemon=True).start()
    threading.Thread(target=contract_ws,      daemon=True).start()
    threading.Thread(target=snapshot_loop,    daemon=True).start()
    threading.Thread(target=upload_sql,       daemon=True).start()
    while True:
        log.info("💓 Main heartbeat OK")
        time.sleep(60)
