# -*- coding: utf-8 -*-
# Bitfinex：現貨 tBTCUST / USDT 永續 tBTCF0:USTF0（UST = USDT；代號超過 3 碼時中間多一個冒號，如 tDOGE:UST）
from rest_ticker_common import base_of, get_json, run, to_float

TICKERS_URL = "https://api-pub.bitfinex.com/v2/tickers?symbols=ALL"


def _native_map(symbols, spot):
    native = {}
    for symbol in symbols:
        base = base_of(symbol)
        if spot:
            native[f"t{base}UST"] = symbol
            native[f"t{base}:UST"] = symbol
        else:
            native[f"t{base}F0:USTF0"] = symbol
    return native


def _collect(symbols, spot):
    native = _native_map(symbols, spot)
    result = {}
    # 每筆為 [SYMBOL, BID, BID_SIZE, ASK, ASK_SIZE, ...]
    for row in get_json(TICKERS_URL):
        symbol = native.get(row[0])
        if symbol:
            bid, ask = to_float(row[1]), to_float(row[3])
            if bid and ask:
                result[symbol] = (bid, ask)
    return result


def fetch_spot(symbols):
    return _collect(symbols, spot=True)


def fetch_contract(symbols):
    return _collect(symbols, spot=False)


if __name__ == "__main__":
    run("bitfinex", fetch_spot, fetch_contract)
