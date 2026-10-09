# -*- coding: utf-8 -*-
# Poloniex：現貨 BTC_USDT / USDT 永續 BTC_USDT_PERP
from rest_ticker_common import base_of, collect, get_json, run

SPOT_URL = "https://api.poloniex.com/markets/ticker24h"
CONTRACT_URL = "https://api.poloniex.com/v3/market/tickers"


def fetch_spot(symbols):
    native = {f"{base_of(s)}_USDT": s for s in symbols}
    return collect(get_json(SPOT_URL), native, "symbol", "bid", "ask")


def fetch_contract(symbols):
    native = {f"{base_of(s)}_USDT_PERP": s for s in symbols}
    return collect(get_json(CONTRACT_URL)["data"], native, "s", "bPx", "aPx")


if __name__ == "__main__":
    run("poloniex", fetch_spot, fetch_contract)
