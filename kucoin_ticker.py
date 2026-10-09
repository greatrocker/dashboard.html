# -*- coding: utf-8 -*-
# KuCoin：現貨 BTC-USDT / USDT 永續 XBTUSDTM（BTC 在合約端叫 XBT）
from rest_ticker_common import base_of, collect, get_json, run

SPOT_URL = "https://api.kucoin.com/api/v1/market/allTickers"
CONTRACT_URL = "https://api-futures.kucoin.com/api/v1/allTickers"


def fetch_spot(symbols):
    native = {f"{base_of(s)}-USDT": s for s in symbols}
    return collect(get_json(SPOT_URL)["data"]["ticker"], native, "symbol", "buy", "sell")


def fetch_contract(symbols):
    native = {f"{base_of(s).replace('BTC', 'XBT')}USDTM": s for s in symbols}
    return collect(get_json(CONTRACT_URL)["data"], native, "symbol", "bestBidPrice", "bestAskPrice")


if __name__ == "__main__":
    run("kucoin", fetch_spot, fetch_contract)
