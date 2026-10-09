# -*- coding: utf-8 -*-
# Toobit：現貨 BTCUSDT / USDT 永續 BTC-SWAP-USDT
from rest_ticker_common import base_of, collect, get_json, run

SPOT_URL = "https://api.toobit.com/quote/v1/ticker/bookTicker"
CONTRACT_URL = "https://api.toobit.com/quote/v1/contract/ticker/bookTicker"


def fetch_spot(symbols):
    return collect(get_json(SPOT_URL), {s: s for s in symbols}, "s", "b", "a")


def fetch_contract(symbols):
    native = {f"{base_of(s)}-SWAP-USDT": s for s in symbols}
    return collect(get_json(CONTRACT_URL), native, "s", "b", "a")


if __name__ == "__main__":
    run("toobit", fetch_spot, fetch_contract)
