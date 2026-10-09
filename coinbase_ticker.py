# -*- coding: utf-8 -*-
# Coinbase：現貨 BTC-USDT（Coinbase Exchange）/ 永續 BTC-PERP（Coinbase International，USDC 計價）
# 兩邊都只有單一幣種查詢 API，所以用 fetch_each 平行查詢，輪詢間隔放寬到 3 秒避免撞 rate limit
from datetime import datetime, timezone

from rest_ticker_common import base_of, fetch_each, get_json, run, to_float

SPOT_URL = "https://api.exchange.coinbase.com/products/{base}-USDT/ticker"
CONTRACT_URL = "https://api.international.coinbase.com/api/v1/instruments/{base}-PERP/quote"
QUOTE_MAX_AGE_SECONDS = 60   # Coinbase International 有些合約報價會凍結數天，超過此秒數的報價視為無效


def quote_age_seconds(item):
    """報價自帶的時間戳記距今幾秒；沒有時間戳記回傳 None。"""
    ts = item.get("timestamp")
    if not ts:
        return None
    quoted = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - quoted).total_seconds()


def _spot_one(symbol):
    item = get_json(SPOT_URL.format(base=base_of(symbol)))
    bid, ask = to_float(item.get("bid")), to_float(item.get("ask"))
    return (bid, ask) if bid and ask else None


def _contract_one(symbol):
    item = get_json(CONTRACT_URL.format(base=base_of(symbol)))
    age = quote_age_seconds(item)
    if age is not None and age > QUOTE_MAX_AGE_SECONDS:
        return None   # 凍結的報價（例如 NEAR-PERP 停在 10/01），不寫入
    bid, ask = to_float(item.get("best_bid_price")), to_float(item.get("best_ask_price"))
    return (bid, ask) if bid and ask else None


def fetch_spot(symbols):
    return fetch_each(symbols, _spot_one)


def fetch_contract(symbols):
    return fetch_each(symbols, _contract_one)


if __name__ == "__main__":
    run("coinbase", fetch_spot, fetch_contract, poll_interval=3)
