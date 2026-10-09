# -*- coding: utf-8 -*-
# Pionex：現貨 BTC_USDT / USDT 永續 BTC_USDT_PERP
from rest_ticker_common import base_of, collect, get_json, run

SPOT_URL = "https://api.pionex.com/api/v1/market/bookTickers?type=SPOT"
CONTRACT_URL = "https://api.pionex.com/api/v1/market/bookTickers?type=PERP"


def fetch_spot(symbols):
    native = {f"{base_of(s)}_USDT": s for s in symbols}
    return collect(get_json(SPOT_URL)["data"]["tickers"], native, "symbol", "bidPrice", "askPrice")


def fetch_contract(symbols):
    native = {f"{base_of(s)}_USDT_PERP": s for s in symbols}
    return collect(get_json(CONTRACT_URL)["data"]["tickers"], native, "symbol", "bidPrice", "askPrice")


if __name__ == "__main__":
    run("pionex", fetch_spot, fetch_contract)
