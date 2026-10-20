"""汇率折算工具：与 summary / research 保持同一口径。

HKD 没有独立行情，按联系汇率 ~7.8 HKD/USD 近似折算；
所有折算先换成 CNY 再换目标币种。
"""
from sqlmodel import Session

from models import Currency, FxRate

HKD_PEG = 7.8
DEFAULT_USDCNY = 7.2


def cached_usdcny(session: Session) -> float:
    """读取缓存的 1 USD = ? CNY；缺失时用默认值，不触发网络请求。"""
    rate = session.get(FxRate, "USDCNY")
    return rate.rate if rate and rate.rate else DEFAULT_USDCNY


def rate_between(session: Session, src: Currency, dst: Currency) -> float:
    """1 单位 src 折合多少 dst。"""
    src = Currency(src)
    dst = Currency(dst)
    if src == dst:
        return 1.0
    usdcny = cached_usdcny(session)
    to_cny = {
        Currency.CNY: 1.0,
        Currency.USD: usdcny,
        Currency.HKD: usdcny / HKD_PEG,
    }
    return to_cny[src] / to_cny[dst]
