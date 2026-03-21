# bybit_ticker.py (原 main.py)
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
# 設定 Logger（使用 RotatingFileHandler）
# ==============================
os.makedirs(LOG_DIR, exist_ok=True)
log_file = f"{LOG_DIR}/{EXCHANGE}_ticker.log"

# 建立 RotatingFileHandler
file_handler = RotatingFileHandler(
    log_file,
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5,           # 保留 5 個備份
    encoding='utf-8'
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
))

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
))

# 設定 root logger
logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler]
)

log = logging.getLogger(__name__)

log.info(f"🚀 {CURRENT_EXCHANGE['display_name']} Ticker 啟動")
log.info(f"📊 交易所: {EXCHANGE}")
log.info(f"📋 DB TABLE: {CURRENT_EXCHANGE['db_table']}")
log.info(f"📦 SP: {CURRENT_EXCHANGE['sp_name']}")
log.info(f"💾 Log 檔案: {log_file} (最多 10MB × 6 個)")

# ==============================
# 全域最新價格
# ==============================
latest_prices = {
    symbol: {
        "Spot_bids": None,
        "Spot_asks": None,
        "Contract_bids": None,
        "Contract_asks": None
    }
    for symbol in SYMBOLS
}

data_queue = queue.Queue()

# ==============================
# Telegram 告警
# ==============================
def send_telegram(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)
        log.info(f"📨 Telegram 告警已送出：{msg}")
    except Exception as e:
        log.warning(f"Telegram 送出失敗：{e}")

# ==============================
# TCP 心跳 Server
# ==============================
def heartbeat_server():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", HEARTBEAT_PORT))
    srv.listen(5)
    log.info(f"💓 TCP 心跳 Server 啟動：port {HEARTBEAT_PORT}")
    while True:
        try:
            conn, addr = srv.accept()
            conn.close()
        except Exception:
            pass

# ==============================
# Spot WebSocket（支援 Bybit）
# ==============================
def on_open_spot(ws):
    # Bybit 訂閱格式
    if EXCHANGE == "bybit":
        args = [CURRENT_EXCHANGE["orderbook_topic_template"].format(symbol=s) for s in SYMBOLS]
        ws.send(json.dumps({"op": "subscribe", "args": args}))
    log.info("🟢 Spot 訂閱成功")

def on_message_spot(ws, message):
    msg = json.loads(message)
    
    # Bybit ping/pong
    if EXCHANGE == "bybit":
        if msg.get("op") == "ping":
            ws.send(json.dumps({"op": "pong"}))
            return
        
        if "topic" in msg and "orderbook" in msg["topic"]:
            symbol = msg["topic"].split(".")[-1]
            if symbol not in latest_prices:
                return
            data = msg["data"]
            bids = data.get("b", [])
            asks = data.get("a", [])
            if bids:
                latest_prices[symbol]["Spot_bids"] = float(bids[0][0])
            if asks:
                latest_prices[symbol]["Spot_asks"] = float(asks[0][0])

def on_error_spot(ws, error):
    log.error(f"❌ Spot WebSocket 錯誤：{error}")

def on_close_spot(ws, code, msg):
    log.warning(f"⚠️ Spot WebSocket 斷線 (code={code})，5秒後重連...")
    send_telegram(f"⚠️ {CURRENT_EXCHANGE['name']} Spot WebSocket 斷線，正在重連...")

def spot_ws():
    while True:
        try:
            ws = websocket.WebSocketApp(
                CURRENT_EXCHANGE["ws_spot_url"],
                on_open=on_open_spot,
                on_message=on_message_spot,
                on_error=on_error_spot,
                on_close=on_close_spot
            )
            ws.run_forever(ping_interval=30, ping_timeout=10)
        except Exception as e:
            log.error(f"Spot WS 例外：{e}")
        time.sleep(5)

# ==============================
# Contract WebSocket（支援 Bybit）
# ==============================
def on_open_contract(ws):
    if EXCHANGE == "bybit":
        args = [CURRENT_EXCHANGE["orderbook_topic_template"].format(symbol=s) for s in SYMBOLS]
        ws.send(json.dumps({"op": "subscribe", "args": args}))
    log.info("🟢 Contract 訂閱成功")

def on_message_contract(ws, message):
    msg = json.loads(message)
    
    if EXCHANGE == "bybit":
        if msg.get("op") == "ping":
            ws.send(json.dumps({"op": "pong"}))
            return
        
        if "topic" in msg and "orderbook" in msg["topic"]:
            symbol = msg["topic"].split(".")[-1]
            if symbol not in latest_prices:
                return
            data = msg["data"]
            bids = data.get("b", [])
            asks = data.get("a", [])
            if bids:
                latest_prices[symbol]["Contract_bids"] = float(bids[0][0])
            if asks:
                latest_prices[symbol]["Contract_asks"] = float(asks[0][0])

def on_error_contract(ws, error):
    log.error(f"❌ Contract WebSocket 錯誤：{error}")

def on_close_contract(ws, code, msg):
    log.warning(f"⚠️ Contract WebSocket 斷線 (code={code})，5秒後重連...")
    send_telegram(f"⚠️ {CURRENT_EXCHANGE['name']} Contract WebSocket 斷線，正在重連...")

def contract_ws():
    while True:
        try:
            ws = websocket.WebSocketApp(
                CURRENT_EXCHANGE["ws_contract_url"],
                on_open=on_open_contract,
                on_message=on_message_contract,
                on_error=on_error_contract,
                on_close=on_close_contract
            )
            ws.run_forever(ping_interval=30, ping_timeout=10)
        except Exception as e:
            log.error(f"Contract WS 例外：{e}")
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
                rows.append({
                    "Time": Time,
                    "symbol": symbol,
                    "Spot_bids":     prices["Spot_bids"],
                    "Spot_asks":     prices["Spot_asks"],
                    "Contract_bids": prices["Contract_bids"],
                    "Contract_asks": prices["Contract_asks"]
                })
            else:
                log.debug(f"⚠️ {symbol} 資料尚未就緒，略過")

        if rows:
            df = pd.DataFrame(rows)
            data_queue.put(df)
            log.info(f"📦 Snapshot 推入 queue：{len(rows)} 個幣種")

        time.sleep(1)

# ==============================
# MSSQL 上傳
# ==============================
def get_conn():
    return pyodbc.connect(
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={MSSQL_SERVER};"
        f"DATABASE={MSSQL_DATABASE};"
        f"UID={MSSQL_USER};"
        f"PWD={MSSQL_PASSWORD};"
        f"Encrypt=no;TrustServerCertificate=yes;",
        autocommit=True
    )

def upload_sql():
    conn   = None
    cursor = None

    while True:
        if conn is None:
            try:
                conn   = get_conn()
                cursor = conn.cursor()
                log.info("✅ MSSQL 已連線")
                send_telegram(f"✅ {CURRENT_EXCHANGE['display_name']}：MSSQL 連線成功，服務啟動")
            except Exception as e:
                log.error(f"MSSQL 連線失敗：{e}，10秒後重試...")
                send_telegram(f"❌ {CURRENT_EXCHANGE['name']} MSSQL 連線失敗：{e}")
                time.sleep(10)
                continue

        try:
            df = data_queue.get(timeout=5)

            for _, row in df.iterrows():
                sp_call = f"""
                    EXEC {CURRENT_EXCHANGE['sp_name']}
                        @p_time = ?,
                        @p_symbol = ?,
                        @p_Spot_bids = ?,
                        @p_Spot_asks = ?,
                        @p_Contract_bids = ?,
                        @p_Contract_asks = ?
                """
                cursor.execute(sp_call, (
                    row['Time'],
                    row['symbol'],
                    row['Spot_bids'],
                    row['Spot_asks'],
                    row['Contract_bids'],
                    row['Contract_asks']
                ))

            log.info(f"📤 已寫入 MSSQL：{len(df)} 筆")

        except queue.Empty:
            pass
        except Exception as e:
            log.error(f"MSSQL 寫入失敗：{e}，嘗試重連...")
            send_telegram(f"❌ {CURRENT_EXCHANGE['name']} MSSQL 寫入失敗：{e}")
            try:
                conn.close()
            except Exception:
                pass
            conn   = None
            cursor = None
            time.sleep(5)

# ==============================
# 主程式
# ==============================
if __name__ == '__main__':
    log.info(f"🚀 {CURRENT_EXCHANGE['display_name']} Ticker 啟動")
    send_telegram(f"🚀 {CURRENT_EXCHANGE['display_name']} 容器已啟動")

    threading.Thread(target=heartbeat_server, daemon=True).start()
    threading.Thread(target=spot_ws,          daemon=True).start()
    threading.Thread(target=contract_ws,      daemon=True).start()
    threading.Thread(target=snapshot_loop,    daemon=True).start()
    threading.Thread(target=upload_sql,       daemon=True).start()

    while True:
        log.info("💓 主程式心跳正常")
        time.sleep(60)
