# -*- coding: utf-8 -*-
"""即時訂單簿查詢 + 可套利金額計算（給 signal_detector 過濾低流動性用）。

fetch_book(exchange_id, market, symbol) -> (bids, asks)
    market: "spot" 或 "contract"；symbol: BTCUSDT
    bids 由高到低、asks 由低到高，每檔為 (價格, 幣量)；合約的「張」已換算成幣量。
arbitrage_capacity(spot_asks, contract_bids, min_gap_pct) -> (可套利金額 USDT, 可套利幣量)
"""
import threading
import time
from datetime import datetime, timezone

from rest_ticker_common import base_of, get_json

LEVELS = 20
SPEC_TTL = 6 * 3600   # 合約規格（每張幾顆幣）快取 6 小時


def _levels(rows, price_idx=0, qty_idx=1, qty_scale=1.0, price_scale=1.0):
    out = []
    for r in rows:
        p, q = float(r[price_idx]) / price_scale, float(r[qty_idx]) * qty_scale
        if p > 0 and q > 0:
            out.append((p, q))
    return out


def _sorted(bids, asks):
    return sorted(bids, key=lambda x: -x[0])[:LEVELS], sorted(asks, key=lambda x: x[0])[:LEVELS]


# ---------- 合約規格：每張合約代表幾顆幣 ----------
# 規格清單很大（下載 1~5 秒以上），由 preload_specs() 在背景預先載入並定期更新；
# 同一份規格同時只會有一個執行緒下載，其他執行緒等它完成。
_spec_cache = {}
_spec_locks = {}
_spec_locks_guard = threading.Lock()


def _spec(key, loader):
    """loader() -> {合約代號: 每張幣量}，整包快取。"""
    hit = _spec_cache.get(key)
    if hit and time.time() - hit[0] < SPEC_TTL:
        return hit[1]
    with _spec_locks_guard:
        lock = _spec_locks.setdefault(key, threading.Lock())
    with lock:
        hit = _spec_cache.get(key)
        if hit and time.time() - hit[0] < SPEC_TTL:
            return hit[1]
        table = loader()
        _spec_cache[key] = (time.time(), table)
        return table


def _okx_ctval():
    return {i["instId"]: float(i["ctVal"]) for i in get_json(
        "https://www.okx.com/api/v5/public/instruments", params={"instType": "SWAP"})["data"]}


def _htx_ctval():
    return {i["contract_code"]: float(i["contract_size"]) for i in get_json(
        "https://api.hbdm.com/linear-swap-api/v1/swap_contract_info")["data"]}


def _kucoin_ctval():
    return {i["symbol"]: float(i["multiplier"]) for i in get_json(
        "https://api-futures.kucoin.com/api/v1/contracts/active")["data"]}


def _gate_ctval():
    return {i["name"]: float(i["quanto_multiplier"]) for i in get_json(
        "https://api.gateio.ws/api/v4/futures/usdt/contracts")}


def _mexc_ctval():
    return {i["symbol"]: float(i["contractSize"]) for i in get_json(
        "https://contract.mexc.com/api/v1/contract/detail")["data"]}


def _toobit_ctval():
    return {c["symbol"]: float(c["contractMultiplier"]) for c in get_json(
        "https://api.toobit.com/api/v1/exchangeInfo").get("contracts", [])}


def _first_ok(codes, fetch):
    """交易所代號有多種寫法時依序嘗試，第一個成功且有資料的為準。"""
    for code in codes:
        try:
            result = fetch(code)
        except Exception:
            continue
        if result and result[0] and result[1]:
            return result
    return [], []


def _xt_ctval():
    return {i["symbol"]: float(i["contractSize"]) for i in get_json(
        "https://fapi.xt.com/future/market/v1/public/symbol/list")["result"]}


# ---------- 各交易所訂單簿 ----------
KRAKEN_BASE = {"BTC": "XBT", "DOGE": "XDG"}


def _binance(symbol, market):
    url = "https://api.binance.com/api/v3/depth" if market == "spot" else "https://fapi.binance.com/fapi/v1/depth"
    b = get_json(url, params={"symbol": symbol, "limit": 20})
    return _levels(b["bids"]), _levels(b["asks"])


def _bybit(symbol, market):
    b = get_json("https://api.bybit.com/v5/market/orderbook",
                 params={"category": "spot" if market == "spot" else "linear", "symbol": symbol, "limit": 50})["result"]
    return _levels(b["b"]), _levels(b["a"])


def _okx(symbol, market):
    inst = f"{base_of(symbol)}-USDT" + ("" if market == "spot" else "-SWAP")
    b = get_json("https://www.okx.com/api/v5/market/books", params={"instId": inst, "sz": 20})["data"][0]
    k = 1.0 if market == "spot" else _spec("okx", _okx_ctval)[inst]
    return _levels(b["bids"], qty_scale=k), _levels(b["asks"], qty_scale=k)


def _mexc(symbol, market):
    if market == "spot":
        b = get_json("https://api.mexc.com/api/v3/depth", params={"symbol": symbol, "limit": 20})
        return _levels(b["bids"]), _levels(b["asks"])
    code = f"{base_of(symbol)}_USDT"
    b = get_json(f"https://contract.mexc.com/api/v1/contract/depth/{code}", params={"limit": 20})["data"]
    k = _spec("mexc", _mexc_ctval)[code]
    return _levels(b["bids"], qty_scale=k), _levels(b["asks"], qty_scale=k)


def _gate(symbol, market):
    pair = f"{base_of(symbol)}_USDT"
    if market == "spot":
        b = get_json("https://api.gateio.ws/api/v4/spot/order_book", params={"currency_pair": pair, "limit": 20})
        return _levels(b["bids"]), _levels(b["asks"])
    b = get_json("https://api.gateio.ws/api/v4/futures/usdt/order_book", params={"contract": pair, "limit": 20})
    k = _spec("gate", _gate_ctval)[pair]
    return ([(float(x["p"]), float(x["s"]) * k) for x in b["bids"]],
            [(float(x["p"]), float(x["s"]) * k) for x in b["asks"]])


def _bitget(symbol, market):
    if market == "spot":
        b = get_json("https://api.bitget.com/api/v2/spot/market/orderbook",
                     params={"symbol": symbol, "type": "step0", "limit": 20})["data"]
    else:
        b = get_json("https://api.bitget.com/api/v2/mix/market/merge-depth",
                     params={"symbol": symbol, "productType": "usdt-futures", "limit": 15})["data"]
    return _levels(b["bids"]), _levels(b["asks"])


def _kucoin(symbol, market):
    if market == "spot":
        b = get_json("https://api.kucoin.com/api/v1/market/orderbook/level2_20",
                     params={"symbol": f"{base_of(symbol)}-USDT"})["data"]
        return _levels(b["bids"]), _levels(b["asks"])
    code = f"{base_of(symbol).replace('BTC', 'XBT')}USDTM"
    b = get_json("https://api-futures.kucoin.com/api/v1/level2/depth20", params={"symbol": code})["data"]
    k = _spec("kucoin", _kucoin_ctval)[code]
    return _levels(b["bids"], qty_scale=k), _levels(b["asks"], qty_scale=k)


def _htx(symbol, market):
    if market == "spot":
        b = get_json("https://api.huobi.pro/market/depth", params={"symbol": symbol.lower(), "type": "step0", "depth": 20})["tick"]
        return _levels(b["bids"]), _levels(b["asks"])
    code = f"{base_of(symbol)}-USDT"
    b = get_json("https://api.hbdm.com/linear-swap-ex/market/depth", params={"contract_code": code, "type": "step0"})["tick"]
    k = _spec("htx", _htx_ctval)[code]
    return _levels(b["bids"], qty_scale=k), _levels(b["asks"], qty_scale=k)


def _bingx(symbol, market):
    pair = f"{base_of(symbol)}-USDT"
    if market == "spot":
        b = get_json("https://open-api.bingx.com/openApi/spot/v1/market/depth",
                     params={"symbol": pair, "limit": 20, "timestamp": int(time.time() * 1000)})["data"]
        return _levels(b["bids"]), _levels(b["asks"])
    b = get_json("https://open-api.bingx.com/openApi/swap/v2/quote/depth", params={"symbol": pair, "limit": 20})["data"]
    return _levels(b["bidsCoin"]), _levels(b["asksCoin"])   # bidsCoin：以幣計的數量


def _cryptocom(symbol, market):
    inst = f"{base_of(symbol)}_USDT" if market == "spot" else f"{base_of(symbol)}USD-PERP"
    b = get_json("https://api.crypto.com/exchange/v1/public/get-book",
                 params={"instrument_name": inst, "depth": 20})["result"]["data"][0]
    return _levels(b["bids"]), _levels(b["asks"])


def _kraken(symbol, market):
    base = base_of(symbol)
    kbase = KRAKEN_BASE.get(base, base)
    if market == "spot":
        def spot(pair):
            res = get_json("https://api.kraken.com/0/public/Depth", params={"pair": pair, "count": 20})["result"]
            b = next(iter(res.values()))
            return _levels(b["bids"]), _levels(b["asks"])
        return _first_ok([f"{kbase}USDT", f"{base}USDT"], spot)

    def contract(code):
        b = get_json("https://futures.kraken.com/derivatives/api/v3/orderbook", params={"symbol": code})["orderBook"]
        return _sorted(_levels(b["bids"]), _levels(b["asks"]))   # Kraken 合約 bids 由低到高，需重排
    return _first_ok([f"PF_{kbase}USD", f"PF_{base}USD"], contract)


def _coinbase(symbol, market):
    base = base_of(symbol)
    if market == "spot":
        def spot(product):
            b = get_json(f"https://api.exchange.coinbase.com/products/{product}/book", params={"level": 2})
            return _levels(b["bids"]), _levels(b["asks"])
        return _first_ok([f"{base}-USDT"], spot)   # 沒有這個交易對時回傳空訂單簿
    # Coinbase International 公開 API 只有最佳一檔；報價凍結（時間戳記過舊）時視為沒有掛單
    q = get_json(f"https://api.international.coinbase.com/api/v1/instruments/{base}-PERP/quote")
    if q.get("timestamp"):
        quoted = datetime.fromisoformat(q["timestamp"].replace("Z", "+00:00"))
        if (datetime.now(timezone.utc) - quoted).total_seconds() > 60:
            return [], []
    return (_levels([(q["best_bid_price"], q["best_bid_size"])]),
            _levels([(q["best_ask_price"], q["best_ask_size"])]))


def _bitfinex(symbol, market):
    base = base_of(symbol)
    codes = [f"t{base}UST", f"t{base}:UST"] if market == "spot" else [f"t{base}F0:USTF0"]

    def book(code):
        rows = get_json(f"https://api-pub.bitfinex.com/v2/book/{code}/P0", params={"len": 25})
        # 每檔 [價格, 筆數, 數量]，數量 > 0 為買單、< 0 為賣單
        bids = [(float(p), float(a)) for p, _, a in rows if a > 0]
        asks = [(float(p), -float(a)) for p, _, a in rows if a < 0]
        return _sorted(bids, asks)
    return _first_ok(codes, book)


def _whitebit(symbol, market):
    code = f"{base_of(symbol)}_USDT" if market == "spot" else f"{base_of(symbol)}_PERP"
    b = get_json(f"https://whitebit.com/api/v4/public/orderbook/{code}", params={"limit": 20})
    return _levels(b["bids"]), _levels(b["asks"])


def _xt(symbol, market):
    code = f"{base_of(symbol).lower()}_usdt"
    if market == "spot":
        b = get_json("https://sapi.xt.com/v4/public/depth", params={"symbol": code, "limit": 20})["result"]
        return _levels(b["bids"]), _levels(b["asks"])
    b = get_json("https://fapi.xt.com/future/market/v1/public/q/depth", params={"symbol": code, "level": 20})["result"]
    k = _spec("xt", _xt_ctval)[code]
    return _levels(b["b"], qty_scale=k), _levels(b["a"], qty_scale=k)


def _phemex(symbol, market):
    if market == "spot":
        # 現貨價格、數量皆為放大 1e8 的整數（Ep / Ev）
        b = get_json("https://api.phemex.com/md/orderbook", params={"symbol": f"s{symbol}"})["result"]["book"]
        return (_levels(b["bids"], price_scale=1e8, qty_scale=1e-8),
                _levels(b["asks"], price_scale=1e8, qty_scale=1e-8))
    b = get_json("https://api.phemex.com/md/v2/orderbook", params={"symbol": symbol})["result"]["orderbook_p"]
    return _sorted(_levels(b["bids"]), _levels(b["asks"]))


def _poloniex(symbol, market):
    base = base_of(symbol)
    if market == "spot":
        b = get_json(f"https://api.poloniex.com/markets/{base}_USDT/orderBook", params={"limit": 20})
        # 扁平陣列：[價, 量, 價, 量, ...]
        pairs = lambda flat: [(flat[i], flat[i + 1]) for i in range(0, len(flat) - 1, 2)]
        return _levels(pairs(b["bids"])), _levels(pairs(b["asks"]))
    code = f"{base}_USDT_PERP"
    b = get_json("https://api.poloniex.com/v3/market/orderBook", params={"symbol": code, "limit": 20})["data"]
    # Poloniex 的完整合約清單不齊全，改逐一合約查規格並快取
    k = _spec(f"poloniex:{code}", lambda: {code: float(get_json(
        "https://api.poloniex.com/v3/market/instruments", params={"symbol": code})["data"]["ctVal"])})[code]
    return _levels(b["bids"], qty_scale=k), _levels(b["asks"], qty_scale=k)


def _deepcoin(symbol, market):
    inst = f"{base_of(symbol)}-USDT" + ("" if market == "spot" else "-SWAP")
    b = get_json("https://api.deepcoin.com/deepcoin/market/books", params={"instId": inst, "sz": 20})["data"]
    if not b:   # 該交易所沒有這個幣
        return [], []
    # 注意：Deepcoin 訂單簿數量已是幣量（ticker 的 bidSz 才是張數），不需乘 ctVal
    return _levels(b["bids"]), _levels(b["asks"])


def _toobit(symbol, market):
    code = symbol if market == "spot" else f"{base_of(symbol)}-SWAP-USDT"
    b = get_json("https://api.toobit.com/quote/v1/depth", params={"symbol": code, "limit": 20})
    k = 1.0 if market == "spot" else _spec("toobit", _toobit_ctval)[code]   # 合約數量為張數
    return _levels(b["b"], qty_scale=k), _levels(b["a"], qty_scale=k)


def _pionex(symbol, market):
    code = f"{base_of(symbol)}_USDT" + ("" if market == "spot" else "_PERP")
    b = get_json("https://api.pionex.com/api/v1/market/depth", params={"symbol": code, "limit": 20})["data"]
    return _levels(b["bids"]), _levels(b["asks"])


FETCHERS = {
    "binance": _binance, "bybit": _bybit, "okx": _okx, "mexc": _mexc, "gate": _gate,
    "bitget": _bitget, "kucoin": _kucoin, "htx": _htx, "bingx": _bingx, "cryptocom": _cryptocom,
    "kraken": _kraken, "coinbase": _coinbase, "bitfinex": _bitfinex, "whitebit": _whitebit, "xt": _xt,
    "phemex": _phemex, "poloniex": _poloniex, "deepcoin": _deepcoin, "toobit": _toobit, "pionex": _pionex,
}


SPEC_LOADERS = {
    "okx": _okx_ctval, "htx": _htx_ctval, "kucoin": _kucoin_ctval, "gate": _gate_ctval,
    "mexc": _mexc_ctval, "xt": _xt_ctval, "toobit": _toobit_ctval,
}


def preload_specs(log=None):
    """背景執行：載入所有合約規格，之後每 SPEC_TTL 更新一次。失敗的 1 分鐘後重試。"""
    def load_all():
        failed = []
        for key, loader in SPEC_LOADERS.items():
            try:
                table = loader()
                _spec_cache[key] = (time.time(), table)
            except Exception as exc:
                failed.append(f"{key}: {type(exc).__name__}")
        return failed

    def loop():
        while True:
            failed = load_all()
            if log:
                log.info(f"Contract specs loaded ({len(SPEC_LOADERS) - len(failed)}/{len(SPEC_LOADERS)})"
                         + (f", failed: {', '.join(failed)}" if failed else ""))
            time.sleep(60 if failed else SPEC_TTL - 300)

    threading.Thread(target=loop, daemon=True, name="spec-preload").start()


def fetch_book(exchange_id, market, symbol):
    bids, asks = FETCHERS[exchange_id](symbol, market)
    return _sorted(bids, asks)


def arbitrage_capacity(spot_asks, contract_bids, min_gap_pct):
    """現貨賣單（便宜→貴）對合約買單（貴→便宜）逐檔配對，直到 Open Gap <= min_gap_pct。
    回傳 (可套利金額 USDT＝買現貨花費, 可套利幣量, 放空合約收到的金額 USDT)。"""
    i = j = 0
    ask_left = spot_asks[0][1] if spot_asks else 0.0
    bid_left = contract_bids[0][1] if contract_bids else 0.0
    usd = qty = contract_usd = 0.0
    while i < len(spot_asks) and j < len(contract_bids):
        ask, bid = spot_asks[i][0], contract_bids[j][0]
        if (bid - ask) / ask * 100 <= min_gap_pct:
            break
        q = min(ask_left, bid_left)
        usd += q * ask
        contract_usd += q * bid
        qty += q
        ask_left -= q
        bid_left -= q
        if ask_left <= 1e-12:
            i += 1
            ask_left = spot_asks[i][1] if i < len(spot_asks) else 0.0
        if bid_left <= 1e-12:
            j += 1
            bid_left = contract_bids[j][1] if j < len(contract_bids) else 0.0
    return usd, qty, contract_usd


def walk_fill(levels, qty):
    """依序吃訂單簿各檔直到成交 qty 顆，回傳 (成交均價, 實際成交量)。
    前 20 檔不夠時，剩餘數量以最後一檔價格成交（保守估計）。沒有掛單回傳 (None, 0)。"""
    if not levels or qty <= 0:
        return None, 0.0
    left, notional = qty, 0.0
    for price, size in levels:
        take = min(left, size)
        notional += take * price
        left -= take
        if left <= 1e-12:
            break
    if left > 1e-12:
        notional += left * levels[-1][0]
    return notional / qty, qty
