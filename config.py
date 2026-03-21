# config.py
import os

# ==============================
# 交易所設定
# ==============================
EXCHANGE = os.getenv("EXCHANGE", "bybit").lower()  # bybit, binance, okx...

# 各交易所設定
EXCHANGE_CONFIG = {
    "bybit": {
        "name": "Bybit",
        "display_name": "Bybit Market Monitor",
        "db_table": "Bybit",
        "sp_name": "merge_market_data_bybit",
        "ws_spot_url": "wss://stream.bybit.com/v5/public/spot",
        "ws_contract_url": "wss://stream.bybit.com/v5/public/linear",
        "orderbook_topic_template": "orderbook.50.{symbol}",  # {symbol} 會被替換成 BTCUSDT
    },
    "binance": {
        "name": "Binance",
        "display_name": "Binance Market Monitor",
        "db_table": "Binance",
        "sp_name": "merge_market_data_binance",
        "ws_spot_url": "wss://stream.binance.com:9443/ws",
        "ws_contract_url": "wss://fstream.binance.com/ws",
        "orderbook_topic_template": "{symbol_lower}@depth",  # btcusdt@depth
    },
    "okx": {
        "name": "OKX",
        "display_name": "OKX Market Monitor",
        "db_table": "OKX",
        "sp_name": "merge_market_data_okx",
        "ws_spot_url": "wss://ws.okx.com:8443/ws/v5/public",
        "ws_contract_url": "wss://ws.okx.com:8443/ws/v5/public",
        "orderbook_topic_template": "books:{symbol}",  # books:BTC-USDT
    },
}

# 當前交易所配置
if EXCHANGE not in EXCHANGE_CONFIG:
    raise ValueError(f"不支援的交易所: {EXCHANGE}，支援清單: {list(EXCHANGE_CONFIG.keys())}")

CURRENT_EXCHANGE = EXCHANGE_CONFIG[EXCHANGE]

# ==============================
# 幣種清單
# ==============================
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
    "SUIUSDT", "TONUSDT", "TRXUSDT", "NEARUSDT", "APTUSDT"
]

# ==============================
# MSSQL 連線設定
# ==============================
MSSQL_SERVER   = os.getenv("MSSQL_SERVER",   "host.docker.internal")
MSSQL_DATABASE = os.getenv("MSSQL_DATABASE", "Crypto")
MSSQL_USER     = os.getenv("MSSQL_USER",     "sa")
MSSQL_PASSWORD = os.getenv("MSSQL_PASSWORD", "1qaz2WSX")

# ==============================
# Telegram 告警設定
# ==============================
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN",   "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ==============================
# 其他設定
# ==============================
HEARTBEAT_PORT = int(os.getenv("HEARTBEAT_PORT", "9000"))
LOG_DIR        = "/app/logs"
