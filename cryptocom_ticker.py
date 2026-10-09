# -*- coding: utf-8 -*-
# Crypto.com：現貨 BTC_USDT / 永續 BTCUSD-PERP（Crypto.com 永續以 USD 計價）
from rest_ticker_common import base_of, collect, get_json, run

TICKERS_URL = "https://api.crypto.com/exchange/v1/public/get-tickers"


def fetch_spot(symbols):
    native = {f"{base_of(s)}_USDT": s for s in symbols}
    return collect(get_json(TICKERS_URL)["result"]["data"], native, "i", "b", "k")


def fetch_contract(symbols):
    native = {f"{base_of(s)}USD-PERP": s for s in symbols}
    return collect(get_json(TICKERS_URL)["result"]["data"], native, "i", "b", "k")


if __name__ == "__main__":
    run("cryptocom", fetch_spot, fetch_contract)
