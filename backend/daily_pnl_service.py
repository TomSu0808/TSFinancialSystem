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
        # 入出金/现金校准不影响投资收益，未来交易不计入当日检查点。
        return _digest(sorted([
            (t.id, t.holding_id, t.date, t.action.value, t.currency.value,
             t.quantity, t.price, t.fee, t.amount)
            for t in txns if t.date <= cutoff and t.action not in ("deposit", "withdraw", "cash_adjust")
        ], key=lambda x: x[0]))

    manual_positions = {
        str(h_id): [currency, quantity, cost_price, cost_value]
        for h_id, currency, quantity, cost_price, cost_value in manual_basis
    }
    basis = {
        "manual": _digest(sorted(manual_basis)),
        "manual_positions": manual_positions,
        "transactions": txn_digest(day),
        "holdings": sorted(h.id for h in holdings
                           if h.asset_type != "cash" and h.id not in excluded),
    }
    old_basis = json.loads(previous.basis_json) if previous else {}
    previous_details = json.loads(previous.details_json or "[]") if previous else []
    has_prev_details = bool(previous_details)
    prev_by_id = {d.get("holding_id"): d for d in previous_details}
    prev_by_key = {}
    duplicate_position_keys = set()
    for detail in previous_details:
        key = detail.get("position_key")
        if not key:
            continue
        if key in prev_by_key:
            duplicate_position_keys.add(key)
            prev_by_key.pop(key, None)
        elif key not in duplicate_position_keys:
            prev_by_key[key] = detail

    rates, usdcny, fx_time = get_to_cny_rates(session)
    fx_stale = fx_time == "unknown" or now - datetime.fromisoformat(fx_time) > timedelta(hours=24)
    uses_fx = any(h.currency != "CNY" and h.asset_type != "cash" for h in holdings)
    complete = not stale and not (uses_fx and fx_stale)

    today_trades = [
        t for t in txns
        if t.date == day and t.action in ("buy", "sell") and t.holding_id is not None
    ]
    today_trade_ids = {t.holding_id for t in today_trades}
    old_manual_positions = old_basis.get("manual_positions")
    opening_note = "期初持仓：由手填持仓转入，不产生现金流；数量为当次交易前持仓。"

    def matches_generated_opening(t):
        if (t.action != "adjust" or t.date != day or t.holding_id not in today_trade_ids
                or t.note != opening_note or old_manual_positions is None):
            return False
        old = old_manual_positions.get(str(t.holding_id))
        if old is None:
            return False
        old_currency, old_quantity, old_cost_price, old_cost_value = old
        expected_price = old_cost_price
        if old_cost_value is not None and old_quantity is not None and old_quantity > 0:
            expected_price = old_cost_value / old_quantity
        return (t.currency.value == old_currency
                and t.quantity == old_quantity
                and t.price == expected_price)

    matching_openings = [t for t in txns if matches_generated_opening(t)]
    generated_opening_ids = set()
    for holding_id in today_trade_ids:
        candidates = [t for t in matching_openings if t.holding_id == holding_id]
        trades = [t for t in today_trades if t.holding_id == holding_id]
        if (len(candidates) == 1 and candidates[0].id is not None
                and any(trade.id is not None and candidates[0].id < trade.id for trade in trades)):
            generated_opening_ids.add(candidates[0].id)

    explicit_adjustment = any(
        t.action == "adjust" and t.date == day and t.id not in generated_opening_ids
        for t in txns
    )
    if old_manual_positions is None:
        manual_changed = old_basis.get("manual") != basis["manual"]
    else:
        manual_ids = set(old_manual_positions) | set(manual_positions)
        changed_manual_ids = {
            int(h_id) for h_id in manual_ids
            if old_manual_positions.get(h_id) != manual_positions.get(h_id)
        }
        manual_changed = bool(changed_manual_ids - today_trade_ids)

    current_non_cash = {
        s["holding_id"]: s for s in snapshots if s["asset_type"] != "cash"
    }
    current_non_cash_ids = set(current_non_cash)
    if has_prev_details:
        previous_non_cash = {
            d.get("holding_id"): d for d in previous_details
            if d.get("asset_type") != "cash" and d.get("holding_id") is not None
        }
        previous_non_cash_ids = set(previous_non_cash)
        added_without_trade = (current_non_cash_ids - previous_non_cash_ids) - today_trade_ids
        removed_positions = previous_non_cash_ids - current_non_cash_ids
        identity_changes = {
            h_id for h_id in current_non_cash_ids & previous_non_cash_ids
            if current_non_cash[h_id].get("position_key")
            != previous_non_cash[h_id].get("position_key")
        }
        holdings_changed = bool(added_without_trade or removed_positions or identity_changes)
    else:
        # 旧记录没有逐仓位明细时，保留原来的保守保护。
        holdings_changed = set(old_basis.get("holdings", [])) != set(basis["holdings"])

    history_changed = old_basis.get("transactions") != txn_digest(yesterday)

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
    elif manual_changed or explicit_adjustment or history_changed or holdings_changed:
        status = "adjusted"
        note = "持仓本金或历史记录发生变更，今日重新建立基准"
    else:
        status = "recorded"
        note = "累计持仓收益的原币种日差额；含已实现盈亏及分红，排除入出金和汇兑变动"

    # 逐仓位日盈亏与总额使用同一口径。新增、缺价或恢复估值的持仓只排除自身，
    # 不再因为可估值范围变化而让其他持仓和整日盈亏全部失效。
    details_total_cny = 0.0
    comparable_count = 0
    partial_income_count = 0
    no_baseline_count = 0
    for s in snapshots:
        s["pnl_native"] = s["pnl_cny"] = s["pnl_usd"] = None
        s["fx_rate"] = usdcny
        s["fx_time"] = fx_time
        s["status"] = status
        if not s["reason"]:
            s["reason"] = note
        if status != "recorded":
            continue
        if s["asset_type"] == "cash":
            s["status"] = "not_applicable"
            s["reason"] = "现金不计入投资盈亏"
            continue

        prev = prev_by_id.get(s["holding_id"])
        if prev is not None and prev.get("position_key") != s["position_key"]:
            prev = None
        if prev is None and s["holding_id"] not in prev_by_id:
            prev = prev_by_key.get(s["position_key"])
        if not has_prev_details or prev is None:
            s["status"] = "no_baseline"
            s["reason"] = "前一日未记录持仓明细" if not has_prev_details else "新增持仓，无前一日基准"
            no_baseline_count += 1
            continue
        if not s["excluded"] and prev.get("excluded", False):
            s["status"] = "no_baseline"
            s["reason"] = "前一日缺价格或成本，今日重新建立持仓基准"
            no_baseline_count += 1
            continue

        if s["excluded"]:
            # 缺少当日估值时，卖出已实现收益可能只是把昨日未实现收益结转，
            # 直接相减会重复计算；分红/利息增量不依赖估值，可以安全计入。
            d_native = s["realized_income"] - (prev.get("realized_income") or 0.0)
        else:
            d_native = s["cumulative"] - (prev.get("cumulative") or 0.0)
        d_cny = d_native * rates[Currency(s["currency"])]
        s["pnl_native"] = round(d_native, 2)
        s["pnl_cny"] = round(d_cny, 2)
        s["pnl_usd"] = round(d_cny / usdcny, 2) if not fx_stale else None
        details_total_cny += d_cny
        if s["excluded"]:
            if d_native:
                partial_income_count += 1
            s["status"] = "excluded"
            specific_reason = s["reason"] or "缺价格或成本"
            s["reason"] = f"{specific_reason}；仅计入分红与利息，卖出盈亏未计入"
        else:
            comparable_count += 1
            s["reason"] = ""

    if status == "recorded":
        if has_prev_details:
            if comparable_count or partial_income_count:
                row.pnl_cny = round(details_total_cny, 2)
                row.pnl_usd = round(details_total_cny / usdcny, 2) if not fx_stale else None
            else:
                status = "missing"
                note = "没有可与前一日比较的持仓，今日建立逐仓位基准"
        else:
            old = json.loads(previous.returns_json)
            delta = sum((native.get(c, 0) - old.get(c, 0)) * rates[Currency(c)]
                        for c in set(native) | set(old))
            row.pnl_cny = round(delta, 2)
            row.pnl_usd = round(delta / usdcny, 2) if not fx_stale else None
        if excluded:
            note += f"；{len(excluded)} 项持仓缺少价格或成本，未计入未实现盈亏"
        if no_baseline_count:
            note += f"；{no_baseline_count} 项持仓无可比基准，未计入"

    row.status = status
    row.note = note
    row.returns_json = json.dumps(native)
    row.basis_json = json.dumps(basis)
    row.details_json = json.dumps(snapshots, ensure_ascii=False)
    row.coverage_complete = complete
    row.updated_at = now
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
