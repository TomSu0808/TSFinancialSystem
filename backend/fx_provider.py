"""汇率抓取：1 USD = ? CNY。

主源用免费、无需 key 的 open.er-api.com（稳定）；失败时回退 akshare 中行牌价。
"""
from typing import Optional

import requests


def fetch_usdcny() -> Optional[float]:
    # 主源：开放汇率 API（免费、无 key）
    try:
        resp = requests.get("https://open.er-api.com/v6/latest/USD", timeout=10)
        resp.raise_for_status()
        rate = resp.json().get("rates", {}).get("CNY")
        if rate:
            return float(rate)
    except Exception:  # noqa: BLE001 — 回退到下一个源
        pass

    # 回退：akshare 中行牌价（取现汇卖出/中间价的一个近似）
    try:
        import akshare as ak

        df = ak.currency_boc_sina(symbol="美元", start_date="20200101", end_date="20991231")
        if df is not None and not df.empty:
            # 取最后一行的中间价/卖出价并换算成 1USD=?CNY（牌价通常按 100 外币计）
            row = df.iloc[-1].to_dict()
            for col in ["中行汇买价", "中行钞买价", "央行中间价"]:
                if col in row and row[col]:
                    return float(row[col]) / 100
    except Exception:  # noqa: BLE001
        pass

    return None
