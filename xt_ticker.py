# -*- coding: utf-8 -*-
# XT.com：現貨 btc_usdt / USDT 永續 btc_usdt（交割合約帶日期後綴，如 btc_usdt_260327，會被略過）
from rest_ticker_common import base_of, collect, get_json, run

SPOT_URL = "https://sapi.xt.com/v4/public/ticker/book"
CONTRACT_URL = "https://fapi.xt.com/future/market/v1/public/q/agg-tickers"


def fetch_spot(symbols):
    native = {f"{base_of(s).lower()}_usdt": s for s in symbols}
    return collect(get_json(SPOT_URL)["result"], native, "s", "bp", "ap")


def fetch_contract(symbols):
    native = {f"{base_of(s).lower()}_usdt": s for s in symbols}
    return collect(get_json(CONTRACT_URL)["result"], native, "s", "bp", "ap")


if __name__ == "__main__":
    run("xt", fetch_spot, fetch_contract)
