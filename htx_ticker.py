# -*- coding: utf-8 -*-
# HTX（Huobi）：現貨 btcusdt / USDT 永續 BTC-USDT
from rest_ticker_common import base_of, collect, get_json, run, to_float

SPOT_URL = "https://api.huobi.pro/market/tickers"
CONTRACT_URL = "https://api.hbdm.com/linear-swap-ex/market/detail/batch_merged?business_type=swap"


def fetch_spot(symbols):
    return collect(get_json(SPOT_URL)["data"], {s.lower(): s for s in symbols}, "symbol", "bid", "ask")


def fetch_contract(symbols):
    native = {f"{base_of(s)}-USDT": s for s in symbols}
    result = {}
    for item in get_json(CONTRACT_URL)["ticks"]:
        symbol = native.get(item.get("contract_code"))
        # bid / ask 格式為 [價格, 數量]
        if symbol and item.get("bid") and item.get("ask"):
            bid, ask = to_float(item["bid"][0]), to_float(item["ask"][0])
            if bid and ask:
                result[symbol] = (bid, ask)
    return result


if __name__ == "__main__":
    run("htx", fetch_spot, fetch_contract)
