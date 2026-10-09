# -*- coding: utf-8 -*-
# Phemex：現貨 sBTCUSDT（價格為 Ep 整數，需除以 1e8）/ USDT 永續 BTCUSDT（Rp 為實際價格）
from rest_ticker_common import collect, get_json, run

SPOT_URL = "https://api.phemex.com/md/spot/ticker/24hr/all"
CONTRACT_URL = "https://api.phemex.com/md/v3/ticker/24hr/all"

SPOT_PRICE_SCALE = 1e8


def fetch_spot(symbols):
    scaled = collect(get_json(SPOT_URL)["result"], {f"s{s}": s for s in symbols}, "symbol", "bidEp", "askEp")
    return {s: (bid / SPOT_PRICE_SCALE, ask / SPOT_PRICE_SCALE) for s, (bid, ask) in scaled.items()}


def fetch_contract(symbols):
    return collect(get_json(CONTRACT_URL)["result"], {s: s for s in symbols}, "symbol", "bidRp", "askRp")


if __name__ == "__main__":
    run("phemex", fetch_spot, fetch_contract)
