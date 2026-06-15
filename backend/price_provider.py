"""按 market 分派的行情抓取。

统一对外接口：fetch_quote(market, symbol) -> {"price": float, "prev_close": float|None}

数据源策略（2026-06 调整）：
- 股票/ETF（A/港/美）主源用「腾讯行情单只接口」 qt.gtimg.cn/q=<code>：
  一次只发一个极小请求，取单只现价/昨收。比 akshare 下载「全市场快照」稳得多、
  快得多——后者上万行分页，在代理/弱网下偶发 RemoteDisconnected 导致整批失败。
- akshare 全市场快照保留为「兜底」，主源失败时再用。
- 场外基金用 akshare 基金净值（本就是单只查询）；加密用 CoinGecko。
- 异常都收敛在调用方（holdings.refresh_prices），这里只管取数。
"""
import time
from typing import Optional

import requests

# ---------------- 腾讯行情（主源） ----------------
_TENCENT_BASE = "https://qt.gtimg.cn/q="


def _a_share_prefix(code: str) -> str:
    """A股/场内基金 代码 -> 腾讯交易所前缀 sh/sz/bj。"""
    c = code.strip()
    # 沪市：股票 60/68，B股 9，可转债 11/110/113，沪市基金/ETF 50/51/56/58
    if c.startswith(("60", "68", "9", "11", "50", "51", "56", "58")):
        return "sh"
    # 深市：股票 00/30，B股 20，可转债 12，深市基金/ETF 15/16/18
    if c.startswith(("00", "30", "20", "12", "15", "16", "18")):
        return "sz"
    # 北交所：4/8 开头
    if c.startswith(("4", "8")):
        return "bj"
    return "sh" if c.startswith("6") else "sz"  # 兜底


def _tencent_code(market: str, symbol: str) -> Optional[str]:
    s = symbol.strip()
    if not s:
        return None
    if market in ("A", "ETF"):
        return _a_share_prefix(s) + s
    if market == "HK":
        return "hk" + s.zfill(5)          # 港股补足 5 位，如 700 -> hk00700
    if market == "US":
        return "us" + s.upper()           # 美股，如 usMSFT
    return None


def _quote_tencent(market: str, symbol: str) -> Optional[dict]:
    code = _tencent_code(market, symbol)
    if not code:
        return None
    r = requests.get(_TENCENT_BASE + code, timeout=10)
    r.encoding = "gbk"                      # 腾讯返回 GBK
    text = r.text.strip()
    if '="' not in text:
        return None
    body = text.split('="', 1)[1].rstrip('";')
    fields = body.split("~")
    # 各市场字段一致：[1]=名称 [3]=现价 [4]=昨收
    if len(fields) < 5 or not fields[3]:
        return None
    try:
        price = float(fields[3])
        prev_close = float(fields[4]) if fields[4] else None
    except ValueError:
        return None
    if price == 0:                          # 0 多为停牌/无效代码
        return None
    return {"price": price, "prev_close": prev_close}


# ---------------- akshare 全市场快照（兜底） ----------------
_SPOT_CACHE: dict = {}
_SPOT_TTL = 60  # 秒


def _first_col(row, candidates):
    for c in candidates:
        if c in row and row[c] not in (None, "", "-"):
            try:
                return float(row[c])
            except (TypeError, ValueError):
                continue
    return None


def _get_spot(market: str):
    import akshare as ak

    now = time.time()
    cached = _SPOT_CACHE.get(market)
    if cached and now - cached[0] < _SPOT_TTL:
        return cached[1]

    if market == "A":
        df = ak.stock_zh_a_spot_em()
    elif market == "HK":
        df = ak.stock_hk_spot_em()
    elif market == "US":
        df = ak.stock_us_spot_em()
    elif market == "ETF":
        df = ak.fund_etf_spot_em()
    else:
        df = None

    _SPOT_CACHE[market] = (now, df)
    return df


def _quote_from_spot(market: str, symbol: str) -> Optional[dict]:
    df = _get_spot(market)
    if df is None or df.empty:
        return None

    code = str(symbol).strip().upper()
    if market == "US":
        mask = df["代码"].astype(str).str.upper().str.split(".").str[-1] == code
    else:
        mask = df["代码"].astype(str).str.upper() == code

    hit = df[mask]
    if hit.empty:
        return None
    row = hit.iloc[0].to_dict()
    price = _first_col(row, ["最新价", "最新价格", "现价"])
    prev_close = _first_col(row, ["昨收", "昨收价", "昨日收盘"])
    return {"price": price, "prev_close": prev_close}


# ---------------- 场外基金 / 加密 ----------------
def _quote_fund(symbol: str) -> Optional[dict]:
    """场外基金：取最近两期单位净值。"""
    import akshare as ak

    try:
        df = ak.fund_open_fund_info_em(symbol=symbol, indicator="单位净值走势")
    except TypeError:
        df = ak.fund_open_fund_info_em(symbol, "单位净值走势")
    if df is None or df.empty:
        return None
    df = df.sort_values(df.columns[0])
    nav_col = "单位净值" if "单位净值" in df.columns else df.columns[1]
    price = float(df.iloc[-1][nav_col])
    prev_close = float(df.iloc[-2][nav_col]) if len(df) >= 2 else None
    return {"price": price, "prev_close": prev_close}


_COINGECKO_IDS = {
    "BTC": "bitcoin", "ETH": "ethereum", "USDT": "tether", "BNB": "binancecoin",
    "SOL": "solana", "XRP": "ripple", "DOGE": "dogecoin", "ADA": "cardano",
}


def _quote_crypto(symbol: str) -> Optional[dict]:
    """加密：CoinGecko 免费接口，取 USD 现价 + 24h 涨跌反推昨收。"""
    coin_id = _COINGECKO_IDS.get(symbol.strip().upper(), symbol.strip().lower())
    resp = requests.get(
        "https://api.coingecko.com/api/v3/simple/price",
        params={"ids": coin_id, "vs_currencies": "usd", "include_24hr_change": "true"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json().get(coin_id)
    if not data:
        return None
    price = float(data["usd"])
    change_pct = data.get("usd_24h_change")
    prev_close = price / (1 + change_pct / 100) if change_pct is not None else None
    return {"price": price, "prev_close": prev_close}


# ---------------- 对外统一入口 ----------------
def fetch_quote(market, symbol: str) -> Optional[dict]:
    """market 可为 Market 枚举或其 value 字符串。"""
    m = getattr(market, "value", market)
    if m in ("A", "HK", "US", "ETF"):
        # 主源：腾讯单只（稳/快）
        try:
            q = _quote_tencent(m, symbol)
            if q:
                return q
        except Exception:  # noqa: BLE001 — 主源失败转兜底
            pass
        # 兜底：akshare 全市场快照
        return _quote_from_spot(m, symbol)
    if m == "FUND":
        return _quote_fund(symbol)
    if m == "CRYPTO":
        return _quote_crypto(symbol)
    return None  # NONE 等不抓价
