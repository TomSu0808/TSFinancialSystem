"""按 UTC 日记录累计收益差；原币种差额按记录时汇率折算，排除本金和汇兑影响。

只比较相邻日、有完整成本/估值且账本口径连续的检查点。不回填不存在的历史。
同时为每个持仓保存逐仓位累计收益快照（details_json），供按日查看明细：
历史仅有汇总、无持仓明细的日期无法反推逐仓位明细，从建立快照起才提供可靠明细。
"""
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta

from sqlmodel import Session, select

from models import Currency, DailyPnl, Holding, Platform, Transaction, profit
from portfolio_context import get_to_cny_rates
from job_locks import serialized_refresh


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def _position_key(h: Holding, platform_name: str) -> str:
    """稳定的仓位标识：基于名称快照，不依赖会因备份恢复而重建的 holding.id。"""
    return f"{platform_name}|{h.symbol}|{h.currency.value}|{h.asset_type.value}"


def _snapshot(h: Holding, platform_name: str, cumulative: float,
              unrealized, is_excluded: bool, reason: str) -> dict:
    """单个持仓当日的累计收益快照（原币）。"""
    return {
        "holding_id": h.id,
        "position_key": _position_key(h, platform_name),
        "platform_id": h.platform_id,
        "platform": platform_name,
        "symbol": h.symbol,
        "name": h.name,
        "asset_type": h.asset_type.value,
        "currency": h.currency.value,
        "unrealized_pnl": unrealized,
        "realized_pnl": h.realized_pnl or 0.0,
        "realized_income": h.realized_income or 0.0,
        "cumulative": round(cumulative, 10),
        "excluded": is_excluded,
        "reason": reason,
    }


@serialized_refresh
def record_daily_pnl(session: Session, user_id: int, now=None) -> DailyPnl:
    now = now or datetime.utcnow()
    day = now.date().isoformat()
    yesterday = (now.date() - timedelta(days=1)).isoformat()
    holdings = session.exec(select(Holding).where(Holding.user_id == user_id)).all()
    txns = session.exec(select(Transaction).where(Transaction.user_id == user_id)).all()
    platforms = {
        p.id: p.name
        for p in session.exec(select(Platform).where(Platform.user_id == user_id)).all()
    }
    previous = session.exec(select(DailyPnl).where(
        DailyPnl.user_id == user_id, DailyPnl.day == yesterday,
    )).first()
    row = session.exec(select(DailyPnl).where(
        DailyPnl.user_id == user_id, DailyPnl.day == day,
    )).first() or DailyPnl(user_id=user_id, day=day)

    native = defaultdict(float)
    excluded = []      # 无法估值（缺价格或成本）的持仓：不计入未实现，但不拦截整日
    stale = []
    manual_basis = []
    snapshots = []
    for h in holdings:
        c = h.currency.value
        realized = (h.realized_pnl or 0) + (h.realized_income or 0)
        native[c] += realized
        platform_name = platforms.get(h.platform_id, f"#{h.platform_id}")
        if h.realized_pnl_incomplete:
            excluded.append(h.id)
            cumulative, unrealized, is_excluded, reason = realized, None, True, "历史卖出缺成本，请补齐原持仓校准的成本"
        elif h.status == "closed" or h.asset_type == "cash":
            cumulative, unrealized, is_excluded, reason = realized, None, False, ""
        else:
            p = profit(h)
            if p is None:
                excluded.append(h.id)
                cumulative, unrealized, is_excluded, reason = realized, None, True, "缺价格或成本"
            else:
                native[c] += p
                cumulative, unrealized, is_excluded, reason = realized + p, p, False, ""
                if h.manual_value is None and (
                    h.price_updated_at is None or now - h.price_updated_at > timedelta(hours=24)
                ):
                    stale.append(h.id)
            if h.source == "manual":
                manual_basis.append((h.id, c, h.quantity, h.cost_price, h.cost_value))
        snapshots.append(_snapshot(h, platform_name, cumulative, unrealized, is_excluded, reason))

    def txn_digest(cutoff):
        # 入出金不影响投资收益，未来交易不计入当日检查点。
        return _digest(sorted([
            (t.id, t.holding_id, t.date, t.action.value, t.currency.value,
             t.quantity, t.price, t.fee, t.amount)
            for t in txns if t.date <= cutoff and t.action not in ("deposit", "withdraw")
        ], key=lambda x: x[0]))

    basis = {"manual": _digest(sorted(manual_basis)), "transactions": txn_digest(day),
             "holdings": sorted(h.id for h in holdings
                                if h.asset_type != "cash" and h.id not in excluded)}
    old_basis = json.loads(previous.basis_json) if previous else {}
    rates, usdcny, fx_time = get_to_cny_rates(session)
    fx_stale = fx_time == "unknown" or now - datetime.fromisoformat(fx_time) > timedelta(hours=24)
    uses_fx = any(h.currency != "CNY" and h.asset_type != "cash" for h in holdings)
    complete = not stale and not (uses_fx and fx_stale)

    row.pnl_cny = row.pnl_usd = None
    if stale or (uses_fx and fx_stale):
        status = "stale"
        note = "行情或汇率未更新，保留检查点但不把旧数据标为当日盈亏"
    elif previous is None:
        status = "baseline"
        note = "缺少前一日基准；已开始记录，历史不补零"
    elif not previous.coverage_complete:
        status = "missing"
        note = "前一日估值不完整，今日重新建立基准"
    elif (old_basis.get("manual") != basis["manual"]
          or any(t.action == "adjust" and t.date == day for t in txns)
          or old_basis.get("transactions") != txn_digest(yesterday)
          or set(old_basis.get("holdings", [])) != set(basis["holdings"])):
        status = "adjusted"
        note = "持仓本金、交易、资产记录或可估值范围发生变更，今日重新建立基准"
    else:
        old = json.loads(previous.returns_json)
        delta = sum((native.get(c, 0) - old.get(c, 0)) * rates[Currency(c)]
                    for c in set(native) | set(old))
        row.pnl_cny = round(delta, 2)
        row.pnl_usd = round(delta / usdcny, 2) if not fx_stale else None
        status = "recorded"
        note = "累计持仓收益的原币种日差额；含已实现盈亏及分红，排除入出金和汇兑变动"
        if excluded:
            note += f"；{len(excluded)} 项持仓缺少价格或成本，未计入"

    row.status = status
    row.note = note

    # 逐仓位日盈亏：使用与当日总额一致的口径（原币累计收益差），按记录时汇率折算。
    previous_details = json.loads(previous.details_json or "[]") if previous else []
    prev_by_id = {d.get("holding_id"): d for d in previous_details}
    has_prev_details = bool(previous_details)

    for s in snapshots:
        s["pnl_native"] = s["pnl_cny"] = s["pnl_usd"] = None
        s["fx_rate"] = usdcny
        s["fx_time"] = fx_time
        s["status"] = status
        if not s["reason"]:
            s["reason"] = note
        if status != "recorded":
            continue
        prev = prev_by_id.get(s["holding_id"])
        if not has_prev_details or prev is None:
            s["status"] = "no_baseline"
            s["reason"] = "前一日未记录持仓明细" if not has_prev_details else "新增持仓，无前一日基准"
            continue
        d_native = s["cumulative"] - (prev.get("cumulative") or 0.0)
        d_cny = d_native * rates[Currency(s["currency"])]
        s["pnl_native"] = round(d_native, 2)
        s["pnl_cny"] = round(d_cny, 2)
        s["pnl_usd"] = round(d_cny / usdcny, 2) if not fx_stale else None
        if s["excluded"]:
            s["status"] = "excluded"
            s["reason"] = "缺价格或成本，仅计入已实现盈亏与分红"
        else:
            s["reason"] = ""

    row.returns_json = json.dumps(native)
    row.basis_json = json.dumps(basis)
    row.details_json = json.dumps(snapshots, ensure_ascii=False)
    row.coverage_complete = complete
    row.updated_at = now
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
