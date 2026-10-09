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
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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

SPOT_TICKER_URL = "https://api.gateio.ws/api/v4/spot/tickers"
CONTRACT_TICKER_URL = "https://api.gateio.ws/api/v4/futures/usdt/tickers"
REQUEST_TIMEOUT = 10
POLL_INTERVAL = 1

# 共用連線（keep-alive）：避免每次輪詢都重新 DNS 查詢 + TLS 握手；
# 短暫 DNS / 連線錯誤由 urllib3 自動重試
http = requests.Session()
http.mount("https://", HTTPAdapter(max_retries=Retry(
    total=4, connect=3, read=1, status=2, backoff_factor=0.5,
    status_forcelist=(429, 500, 502, 503, 504), allowed_methods=frozenset({"GET"}),
)))

os.makedirs(LOG_DIR, exist_ok=True)
log_file = f"{LOG_DIR}/{EXCHANGE}_ticker.log"
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

file_handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
file_handler.setFormatter(formatter)
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

log = logging.getLogger("gate_ticker")
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


def from_gate_symbol(gate_symbol: str) -> str:
    return gate_symbol.replace("_", "")


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


def to_float(value):
    if value in (None, "", "0"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_spot_prices():
    response = http.get(SPOT_TICKER_URL, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    payload = response.json()

    updated = 0
    for item in payload:
        symbol = from_gate_symbol(item.get("currency_pair", ""))
        if symbol not in latest_prices:
            continue
        bid = to_float(item.get("highest_bid"))
        ask = to_float(item.get("lowest_ask"))
        if bid is None or ask is None:
            continue
        latest_prices[symbol]["Spot_bids"] = bid
        latest_prices[symbol]["Spot_asks"] = ask
        updated += 1
    return updated


def fetch_contract_prices():
    response = http.get(CONTRACT_TICKER_URL, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    payload = response.json()

    updated = 0
    for item in payload:
        symbol = from_gate_symbol(item.get("contract", ""))
        if symbol not in latest_prices:
            continue
        bid = to_float(item.get("highest_bid"))
        ask = to_float(item.get("lowest_ask"))
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
            log.error(f"Gate REST fetch failed: {exc}")
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
    if EXCHANGE != "gate":
        raise ValueError("gate_ticker.py requires EXCHANGE=gate")

    log.info(f"{CURRENT_EXCHANGE['display_name']} started (REST snapshot mode)")
    threading.Thread(target=heartbeat_server, daemon=True).start()
    threading.Thread(target=snapshot_loop, daemon=True).start()
    upload_sql()
