"""统一交易字段校验：buy/sell/deposit/withdraw/dividend 的业务规则。

所有 create / update / import commit 都必须经过同一套校验，
避免负数、缺失值污染持仓、现金和收益。
"""
import re
import math
from datetime import datetime as _dt
from typing import List, Optional

from fastapi import HTTPException
from sqlmodel import Session

from models import Currency, Transaction, TxnAction, User

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_transaction(
    session: Session,
    user: User,
    action: TxnAction,
    platform_id: Optional[int],
    currency: Optional[Currency],
    symbol: Optional[str] = None,
    name: Optional[str] = None,
    quantity: Optional[float] = None,
    price: Optional[float] = None,
    fee: Optional[float] = None,
    amount: Optional[float] = None,
    date: Optional[str] = None,
    exclude_txn_id: Optional[int] = None,
) -> None:
    """校验交易字段，不合法时抛出 HTTPException(400)。

    参数说明：
    - exclude_txn_id: 更新场景排除自身，用于 withdraw 余额校验。
    """
    errors: List[str] = []

    # ── 通用校验 ──
    # action 必须有效（TxnAction 枚举已保证，但防御性检查）
    if action not in (TxnAction.buy, TxnAction.sell, TxnAction.adjust, TxnAction.deposit,
                      TxnAction.withdraw, TxnAction.dividend, TxnAction.cash_adjust,
                      TxnAction.other):
        errors.append(f"无效的交易类型: {action}")

    # date 格式
    if date is not None:
        if not date or not _DATE_RE.match(date):
            errors.append(f"日期格式错误（应为 YYYY-MM-DD）：{date}")
        else:
            try:
                _dt.strptime(date, "%Y-%m-%d")
            except ValueError:
                errors.append(f"日期无效：{date}")

    # ── buy / sell 校验 ──
    for field, value in (("数量", quantity), ("价格", price), ("手续费", fee), ("金额", amount)):
        if value is not None and not math.isfinite(value):
            errors.append(f"{field}必须是有限数值")

    if action == TxnAction.adjust:
        if quantity is None or quantity < 0:
            errors.append("校准后的持仓数量必须大于等于 0")
        if not platform_id or not symbol:
            errors.append("持仓校准必须指定平台和代码")
        if fee not in (None, 0) or amount not in (None, 0):
            errors.append("持仓校准不产生现金流，请留空手续费和金额")

    if action in (TxnAction.buy, TxnAction.sell):
        if quantity is None or quantity <= 0:
            errors.append(f"{'买入' if action == TxnAction.buy else '卖出'}数量必须是正数")
        if price is None or price <= 0:
            errors.append(f"{'买入' if action == TxnAction.buy else '卖出'}价格必须是正数")
        if fee is not None and fee < 0:
            errors.append("手续费不能为负数")
        if not platform_id:
            errors.append("买卖交易必须指定平台")
        if not symbol and not name:
            errors.append("买卖交易必须指定代码或名称")

    # ── sell 额外：超卖校验保留在 _check_oversell（transactions.py），此处不做重复 ──

    # ── deposit / withdraw 校验 ──
    if action in (TxnAction.deposit, TxnAction.withdraw):
        eff_amount = amount if amount is not None and amount > 0 else quantity
        if eff_amount is None or eff_amount <= 0:
            errors.append(f"{'入金' if action == TxnAction.deposit else '出金'}金额必须是正数")
        if not platform_id:
            errors.append(f"{'入金' if action == TxnAction.deposit else '出金'}必须指定平台")
        if not currency:
            errors.append(f"{'入金' if action == TxnAction.deposit else '出金'}必须指定币种")
        # 出金负余额校验由 cash_service.check_cash 按时间线统一处理（含编辑/回填/删除）。

    # ── cash_adjust（现金校准/初始化）校验 ──
    if action == TxnAction.cash_adjust:
        if amount is None or amount < 0:
            errors.append("现金校准的余额必须是非负数（填写该时点的绝对余额）")
        if not platform_id:
            errors.append("现金校准必须指定平台")
        if not currency:
            errors.append("现金校准必须指定币种")
        if quantity not in (None, 0) or price not in (None, 0) or fee not in (None, 0):
            errors.append("现金校准不涉及数量/价格/手续费，请留空")

    # ── dividend 校验 ──
    if action == TxnAction.dividend:
        if amount is None or amount <= 0:
            errors.append("分红/利息金额必须是正数")
        if not platform_id:
            errors.append("分红/利息必须指定平台")
        if not currency:
            errors.append("分红/利息必须指定币种")

    # ── 数值防负 ──
    if quantity is not None and quantity < 0:
        errors.append("数量不能为负数")
    if price is not None and price < 0:
        errors.append("价格不能为负数")
    if fee is not None and fee < 0:
        errors.append("手续费不能为负数")
    if amount is not None and amount < 0:
        errors.append("金额不能为负数")

    if errors:
        raise HTTPException(400, "; ".join(errors))
