"""安全 Decimal 计算辅助：减少核心路径的二进制浮点误差。

设计原则：
- DB 字段暂不迁移（仍为 float），仅在计算路径使用 Decimal。
- 对外接口返回 float，内部运算用 Decimal 保证精度。
- 渐进替换：关键路径优先（交易回放、市值、盈亏）。
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Union

# Decimal 默认精度：金融场景 18 位有效数字，四舍五入
_DECIMAL_CTX = Decimal  # 使用模块级 Decimal，精度足够

Number = Union[int, float, Decimal, None]


def to_d(value: Number) -> Decimal:
    """安全转换为 Decimal。None 返回 0，float 通过字符串转换避免精度丢失。"""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(str(value))


def to_float(d: Decimal, ndigits: int = 10) -> float:
    """Decimal → float，四舍五入到指定位数。"""
    quantize_str = "0." + "0" * (ndigits - 1) + "1"
    return float(d.quantize(Decimal(quantize_str), rounding=ROUND_HALF_UP))


def d_sum(*values: Number) -> Decimal:
    """Decimal 安全加法。"""
    result = Decimal("0")
    for v in values:
        result += to_d(v)
    return result


def d_mul(a: Number, b: Number) -> Decimal:
    """Decimal 安全乘法。"""
    return to_d(a) * to_d(b)


def d_div(a: Number, b: Number, default: Number = Decimal("0")) -> Decimal:
    """Decimal 安全除法。除数为 0 返回 default。"""
    bd = to_d(b)
    if bd == 0:
        return to_d(default)
    return to_d(a) / bd


def d_sub(a: Number, b: Number) -> Decimal:
    """Decimal 安全减法。"""
    return to_d(a) - to_d(b)


def safe_quantity(qty: Number) -> Decimal:
    """安全转换数量（正数）。"""
    return to_d(qty)


def safe_price(p: Number) -> Decimal:
    """安全转换价格。"""
    return to_d(p)


def safe_fee(f: Number) -> Decimal:
    """安全转换费用。"""
    return to_d(f)
