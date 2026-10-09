# -*- coding: utf-8 -*-
# Bitget：現貨 BTCUSDT / USDT 永續 BTCUSDT
from rest_ticker_common import collect, get_json, run

SPOT_URL = "https://api.bitget.com/api/v2/spot/market/tickers"
CONTRACT_URL = "https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES"


def fetch_spot(symbols):
    return collect(get_json(SPOT_URL)["data"], {s: s for s in symbols}, "symbol", "bidPr", "askPr")


def fetch_contract(symbols):
    return collect(get_json(CONTRACT_URL)["data"], {s: s for s in symbols}, "symbol", "bidPr", "askPr")


if __name__ == "__main__":
    run("bitget", fetch_spot, fetch_contract)
