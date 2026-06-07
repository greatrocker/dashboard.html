# -*- coding: utf-8 -*-
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


SPOT_BOOK_TICKER_URL = "https://api.mexc.com/api/v3/ticker/bookTicker"
CONTRACT_TICKER_URL = "https://contract.mexc.com/api/v1/contract/ticker"
REQUEST_TIMEOUT = 10
POLL_INTERVAL = 1

os.makedirs(LOG_DIR, exist_ok=True)
log_file = f"{LOG_DIR}/{EXCHANGE}_ticker.log"
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

file_handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
file_handler.setFormatter(formatter)
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

log = logging.getLogger("mexc_ticker")
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
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=REQUEST_TIMEOUT)
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


def from_contract_symbol(symbol: str) -> str:
    return symbol.replace("_", "")


def to_float(value):
    if value in (None, ""):
        return None
    return float(value)


def fetch_spot_prices():
    response = requests.get(SPOT_BOOK_TICKER_URL, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict):
        payload = [payload]

    updated = 0
    for item in payload:
        symbol = item.get("symbol")
        if symbol not in latest_prices:
            continue
        bid = to_float(item.get("bidPrice"))
        ask = to_float(item.get("askPrice"))
        if bid is None or ask is None:
            continue
        latest_prices[symbol]["Spot_bids"] = bid
        latest_prices[symbol]["Spot_asks"] = ask
        updated += 1
    return updated


def fetch_contract_prices():
    response = requests.get(CONTRACT_TICKER_URL, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    body = response.json()
    payload = body.get("data", body)
    if isinstance(payload, dict):
        payload = [payload]

    updated = 0
    for item in payload:
        symbol = from_contract_symbol(item.get("symbol", ""))
        if symbol not in latest_prices:
            continue
        bid = to_float(item.get("bid1"))
        ask = to_float(item.get("ask1"))
        if bid is None or ask is None:
            continue
        latest_prices[symbol]["Contract_bids"] = bid
        latest_prices[symbol]["Contract_asks"] = ask
        updated += 1
    return updated


def snapshot_loop():
    while True:
        try:
            spot_count = fetch_spot_prices()
            contract_count = fetch_contract_prices()
        except Exception as exc:
            log.error(f"MEXC REST fetch failed: {exc}")
            time.sleep(5)
            continue

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rows = []
        ready_count = 0
        for symbol, prices in latest_prices.items():
            if all(value is not None for value in prices.values()):
                rows.append({"Time": now, "symbol": symbol, **prices})
                ready_count += 1

        if rows:
            data_queue.put(pd.DataFrame(rows))
            log.info(
                f"Snapshot: {ready_count}/{len(SYMBOLS)} ready "
                f"(spot={spot_count}, contract={contract_count})"
            )
        else:
            log.info(f"Waiting... 0/{len(SYMBOLS)} ready (spot={spot_count}, contract={contract_count})")

        time.sleep(POLL_INTERVAL)


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
    if EXCHANGE != "mexc":
        raise ValueError("mexc_ticker.py requires EXCHANGE=mexc")

    log.info(f"{CURRENT_EXCHANGE['display_name']} started (REST snapshot mode)")
    threading.Thread(target=heartbeat_server, daemon=True).start()
    threading.Thread(target=snapshot_loop, daemon=True).start()
    upload_sql()
