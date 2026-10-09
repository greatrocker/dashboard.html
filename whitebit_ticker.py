# -*- coding: utf-8 -*-
# WhiteBIT：現貨 BTC_USDT / USDT 永續 BTC_PERP
from rest_ticker_common import base_of, collect, get_json, run, to_float

SPOT_URL = "https://whitebit.com/api/v1/public/tickers"
CONTRACT_URL = "https://whitebit.com/api/v4/public/futures"


def fetch_spot(symbols):
    tickers = get_json(SPOT_URL)["result"]
    result = {}
    for symbol in symbols:
        item = tickers.get(f"{base_of(symbol)}_USDT")
        if item:
            bid, ask = to_float(item["ticker"].get("bid")), to_float(item["ticker"].get("ask"))
            if bid and ask:
                result[symbol] = (bid, ask)
    return result


def fetch_contract(symbols):
    native = {f"{base_of(s)}_PERP": s for s in symbols}
    return collect(get_json(CONTRACT_URL)["result"], native, "ticker_id", "bid", "ask")


if __name__ == "__main__":
    run("whitebit", fetch_spot, fetch_contract)
