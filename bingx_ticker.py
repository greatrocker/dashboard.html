# -*- coding: utf-8 -*-
# BingX：現貨 BTC-USDT / USDT 永續 BTC-USDT
import time

from rest_ticker_common import base_of, collect, get_json, run

SPOT_URL = "https://open-api.bingx.com/openApi/spot/v1/ticker/24hr"
CONTRACT_URL = "https://open-api.bingx.com/openApi/swap/v2/quote/ticker"


def _data(body):
    # BingX 偶爾回傳沒有 data 的錯誤訊息（如限流），把原始內容帶進 log 方便排查
    if "data" not in body:
        raise RuntimeError(f"unexpected BingX response: {str(body)[:200]}")
    return body["data"]


def fetch_spot(symbols):
    native = {f"{base_of(s)}-USDT": s for s in symbols}
    data = _data(get_json(SPOT_URL, params={"timestamp": int(time.time() * 1000)}))
    return collect(data, native, "symbol", "bidPrice", "askPrice")


def fetch_contract(symbols):
    native = {f"{base_of(s)}-USDT": s for s in symbols}
    return collect(_data(get_json(CONTRACT_URL)), native, "symbol", "bidPrice", "askPrice")


if __name__ == "__main__":
    run("bingx", fetch_spot, fetch_contract)
