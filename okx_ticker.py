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

log = logging.getLogger("okx_ticker")
log.setLevel(logging.DEBUG)
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


def to_okx_spot(symbol: str) -> str:
    base = symbol[:-4]
    quote = symbol[-4:]
    return f"{base}-{quote}"


def to_okx_swap(symbol: str) -> str:
    return f"{to_okx_spot(symbol)}-SWAP"


def from_okx_symbol(inst_id: str) -> str:
    if inst_id.endswith("-SWAP"):
        inst_id = inst_id[:-5]
    return inst_id.replace("-", "")


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


def okx_ping(ws):
    while True:
        time.sleep(20)
        try:
            ws.send("ping")
        except Exception:
            break


def subscribe_topics(ws, market_type):
    if market_type == "Spot":
        args = [{"channel": "books5", "instId": to_okx_spot(symbol)} for symbol in SYMBOLS]
    else:
        args = [{"channel": "books5", "instId": to_okx_swap(symbol)} for symbol in SYMBOLS]
    ws.send(json.dumps({"op": "subscribe", "args": args}))
    log.info(f"{market_type} subscribed: {len(args)} symbols")


def on_message(_, message, market_type):
    if message == "pong":
        return

    try:
        msg = json.loads(message)
    except json.JSONDecodeError:
        return

    if msg.get("event") == "subscribe":
        log.info(f"{market_type} subscription acknowledged: {msg}")
        return

    data = msg.get("data", [])
    if not data:
        return

    book = data[0]
    symbol = from_okx_symbol(book.get("instId", ""))
    bids = book.get("bids", [])
    asks = book.get("asks", [])
    if symbol not in latest_prices or not bids or not asks:
        return

    latest_prices[symbol][f"{market_type}_bids"] = float(bids[0][0])
    latest_prices[symbol][f"{market_type}_asks"] = float(asks[0][0])


def run_ws(ws_url, market_type):
    while True:
        try:
            ws = websocket.WebSocketApp(
                ws_url,
                on_open=lambda current_ws: threading.Thread(
                    target=subscribe_topics, args=(current_ws, market_type), daemon=True
                ).start(),
                on_message=lambda current_ws, msg: on_message(current_ws, msg, market_type),
                on_error=lambda current_ws, err: log.error(f"{market_type} WS Error: {err}"),
                on_close=lambda current_ws, status_code, close_msg: log.warning(
                    f"{market_type} WS closed: {status_code} {close_msg}"
                ),
            )
            threading.Thread(target=okx_ping, args=(ws,), daemon=True).start()
            ws.run_forever()
        except Exception as exc:
            log.error(f"{market_type} WS Exception: {exc}")
        time.sleep(5)


def snapshot_loop():
    while True:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rows = []
        ready_count = 0

        for symbol, prices in latest_prices.items():
            if all(value is not None for value in prices.values()):
                rows.append({"Time": now, "symbol": symbol, **prices})
                ready_count += 1

        if rows:
            data_queue.put(pd.DataFrame(rows))
            log.info(f"Snapshot: {ready_count}/{len(SYMBOLS)} symbols ready")
        else:
            log.info(f"Waiting... {ready_count}/{len(SYMBOLS)} symbols ready")

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
                    (
                        row["Time"],
                        row["symbol"],
                        row["Spot_bids"],
                        row["Spot_asks"],
                        row["Contract_bids"],
                        row["Contract_asks"],
                    ),
                )
            log.info(f"Written to MSSQL: {len(df)} rows")
        except queue.Empty:
            pass
        except Exception as exc:
            log.error(f"MSSQL write failed: {exc}")
            conn = None
            cursor = None
            time.sleep(5)


if __name__ == "__main__":
    if EXCHANGE != "okx":
        raise ValueError("okx_ticker.py requires EXCHANGE=okx")

    log.info(f"{CURRENT_EXCHANGE['display_name']} started")
    threading.Thread(target=heartbeat_server, daemon=True).start()
    threading.Thread(target=run_ws, args=(CURRENT_EXCHANGE["ws_spot_url"], "Spot"), daemon=True).start()
    threading.Thread(target=run_ws, args=(CURRENT_EXCHANGE["ws_contract_url"], "Contract"), daemon=True).start()
    threading.Thread(target=snapshot_loop, daemon=True).start()
    upload_sql()
