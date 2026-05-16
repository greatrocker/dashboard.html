# config.py
import os

# ==============================
# 鈭斗??閮剖?
# ==============================
EXCHANGE = os.getenv("EXCHANGE", "bybit").lower()  # bybit, binance, okx...

# ?漱??閮剖?
EXCHANGE_CONFIG = {
    "bybit": {
        "name": "Bybit",
        "display_name": "Bybit Market Monitor",
        "db_table": "Bybit",
        "sp_name": "merge_market_data_bybit",
        "ws_spot_url": "wss://stream.bybit.com/v5/public/spot",
        "ws_contract_url": "wss://stream.bybit.com/v5/public/linear",
        "orderbook_topic_template": "orderbook.50.{symbol}",  # {symbol} ?◤?踵???BTCUSDT
    },
    "binance": {
        "name": "Binance",
        "display_name": "Binance Market Monitor",
        "db_table": "Binance",
        "sp_name": "merge_market_data_binance",
        "ws_spot_url": "wss://stream.binance.com:9443/ws",
        "ws_contract_url": "wss://fstream.binance.com/ws",
        "orderbook_topic_template": "{symbol_lower}@bookTicker",  # btcusdt@bookTicker
    },
    "okx": {
        "name": "OKX",
        "display_name": "OKX Market Monitor",
        "db_table": "OKX",
        "sp_name": "merge_market_data_okx",
        "ws_spot_url": "wss://ws.okx.com:8443/ws/v5/public",
        "ws_contract_url": "wss://ws.okx.com:8443/ws/v5/public",
        "orderbook_topic_template": "books5:{symbol}",  # books5:BTC-USDT
    },
}

# ?嗅?鈭斗???蔭
if EXCHANGE not in EXCHANGE_CONFIG:
    raise ValueError(f"銝?渡?鈭斗??: {EXCHANGE}嚗?湔??? {list(EXCHANGE_CONFIG.keys())}")

CURRENT_EXCHANGE = EXCHANGE_CONFIG[EXCHANGE]

# ==============================
# 撟?車皜
# ==============================
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
    "SUIUSDT", "TONUSDT", "TRXUSDT", "NEARUSDT", "APTUSDT"
]
# SYMBOLS = [
#     "BTCUSDT", "ETHUSDT"
# ]

# ==============================
# MSSQL ???閮剖?
# ==============================
MSSQL_SERVER   = os.getenv("MSSQL_SERVER",   "172.26.0.1,1433")
MSSQL_DATABASE = os.getenv("MSSQL_DATABASE", "Crypto")
MSSQL_USER     = os.getenv("MSSQL_USER",     "sa")
MSSQL_PASSWORD = os.getenv("MSSQL_PASSWORD", "1qaz2WSX")

# ==============================
# Telegram ?郎閮剖?
# ==============================
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN",   "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ==============================
# ?嗡?閮剖?
# ==============================
HEARTBEAT_PORT = int(os.getenv("HEARTBEAT_PORT", "9000"))
LOG_DIR        = "/app/logs"
