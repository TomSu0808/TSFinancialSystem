"""按 UTC 日记录累计收益差；原币种差额按记录时汇率折算，排除本金和汇兑影响。

只比较相邻日、有完整成本/估值且账本口径连续的检查点。不回填不存在的历史。
"""
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta

from sqlmodel import Session, select

from models import DailyPnl, Holding, Transaction, profit
from portfolio_context import get_to_cny_rates
from job_locks import serialized_refresh


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


@serialized_refresh
def record_daily_pnl(session: Session, user_id: int, now=None) -> DailyPnl:
    now = now or datetime.utcnow()
    day = now.date().isoformat()
    yesterday = (now.date() - timedelta(days=1)).isoformat()
    holdings = session.exec(select(Holding).where(Holding.user_id == user_id)).all()
    txns = session.exec(select(Transaction).where(Transaction.user_id == user_id)).all()
    previous = session.exec(select(DailyPnl).where(
        DailyPnl.user_id == user_id, DailyPnl.day == yesterday,
    )).first()
    row = session.exec(select(DailyPnl).where(
        DailyPnl.user_id == user_id, DailyPnl.day == day,
    )).first() or DailyPnl(user_id=user_id, day=day)

    native = defaultdict(float)
    missing = []
    stale = []
    manual_basis = []
    for h in holdings:
        c = h.currency.value
        native[c] += (h.realized_pnl or 0) + (h.realized_income or 0)
        if h.status == "closed" or h.asset_type == "cash":
            continue
        p = profit(h)
        if p is None:
            missing.append(h.id)
        else:
            native[c] += p
        if h.manual_value is None and (
            h.price_updated_at is None or now - h.price_updated_at > timedelta(hours=24)
        ):
            stale.append(h.id)
        if h.source == "manual":
            manual_basis.append((h.id, c, h.quantity, h.cost_price))

    def txn_digest(cutoff):
        # 入出金不影响投资收益，未来交易不计入当日检查点。
        return _digest(sorted([
            (t.id, t.holding_id, t.date, t.action.value, t.currency.value,
             t.quantity, t.price, t.fee, t.amount)
            for t in txns if t.date <= cutoff and t.action not in ("deposit", "withdraw")
        ], key=lambda x: x[0]))

    basis = {"manual": _digest(sorted(manual_basis)), "transactions": txn_digest(day),
             "holdings": sorted(h.id for h in holdings if h.asset_type != "cash")}
    old_basis = json.loads(previous.basis_json) if previous else {}
    rates, usdcny, fx_time = get_to_cny_rates(session)
    fx_stale = fx_time == "unknown" or now - datetime.fromisoformat(fx_time) > timedelta(hours=24)
    uses_fx = any(h.currency != "CNY" and h.asset_type != "cash" for h in holdings)
    complete = not missing and not stale and not (uses_fx and fx_stale)
    row.pnl_cny = row.pnl_usd = None
    if missing:
        row.status, row.note = "missing", f"{len(missing)} 项持仓缺少价格或成本，暂不能计算完整日盈亏"
    elif stale or (uses_fx and fx_stale):
        row.status, row.note = "stale", "行情或汇率未更新，保留检查点但不把旧数据标为当日盈亏"
    elif previous is None:
        row.status, row.note = "baseline", "缺少前一日基准；已开始记录，历史不补零"
    elif not previous.coverage_complete:
        row.status, row.note = "missing", "前一日估值不完整，今日重新建立基准"
    elif (old_basis.get("manual") != basis["manual"]
          or old_basis.get("transactions") != txn_digest(yesterday)
          or not set(old_basis.get("holdings", [])).issubset(basis["holdings"])):
        row.status, row.note = "adjusted", "持仓本金、历史交易或资产记录发生修改，今日重新建立基准"
    else:
        old = json.loads(previous.returns_json)
        from models import Currency
        delta = sum((native.get(c, 0) - old.get(c, 0)) * rates[Currency(c)]
                    for c in set(native) | set(old))
        row.pnl_cny = round(delta, 2)
        row.pnl_usd = round(delta / usdcny, 2) if not fx_stale else None
        row.status = "recorded"
        row.note = "累计持仓收益的原币种日差额；含已实现盈亏及分红，排除入出金和汇兑变动"
    row.returns_json = json.dumps(native)
    row.basis_json = json.dumps(basis)
    row.coverage_complete = complete
    row.updated_at = now
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
