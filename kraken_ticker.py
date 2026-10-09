# -*- coding: utf-8 -*-
# Kraken：現貨 XBTUSDT / 永續 PF_XBTUSD（Kraken Futures 以 USD 計價；BTC=XBT、DOGE=XDG）
from rest_ticker_common import base_of, collect, get_json, run, to_float

SPOT_URL = "https://api.kraken.com/0/public/Ticker"
CONTRACT_URL = "https://futures.kraken.com/derivatives/api/v3/tickers"

KRAKEN_BASE = {"BTC": "XBT", "DOGE": "XDG"}


def fetch_spot(symbols):
    tickers = get_json(SPOT_URL)["result"]
    result = {}
    for symbol in symbols:
        base = base_of(symbol)
        item = tickers.get(f"{KRAKEN_BASE.get(base, base)}USDT") or tickers.get(f"{base}USDT")
        # a / b 格式為 [價格, 整數量, 數量]
        if item:
            bid, ask = to_float(item["b"][0]), to_float(item["a"][0])
            if bid and ask:
                result[symbol] = (bid, ask)
    return result


def fetch_contract(symbols):
    native = {}
    for symbol in symbols:
        base = base_of(symbol)
        native[f"PF_{base}USD"] = symbol
        native[f"PF_{KRAKEN_BASE.get(base, base)}USD"] = symbol
    return collect(get_json(CONTRACT_URL)["tickers"], native, "symbol", "bid", "ask")


if __name__ == "__main__":
    run("kraken", fetch_spot, fetch_contract)
