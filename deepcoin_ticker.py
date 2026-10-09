# -*- coding: utf-8 -*-
# Deepcoin：現貨 BTC-USDT / USDT 永續 BTC-USDT-SWAP
from rest_ticker_common import base_of, collect, get_json, run

SPOT_URL = "https://api.deepcoin.com/deepcoin/market/tickers?instType=SPOT"
CONTRACT_URL = "https://api.deepcoin.com/deepcoin/market/tickers?instType=SWAP"


def fetch_spot(symbols):
    native = {f"{base_of(s)}-USDT": s for s in symbols}
    return collect(get_json(SPOT_URL)["data"], native, "instId", "bidPx", "askPx")


def fetch_contract(symbols):
    native = {f"{base_of(s)}-USDT-SWAP": s for s in symbols}
    return collect(get_json(CONTRACT_URL)["data"], native, "instId", "bidPx", "askPx")


if __name__ == "__main__":
    run("deepcoin", fetch_spot, fetch_contract)
