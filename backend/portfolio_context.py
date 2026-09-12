"""全账户组合分析上下文构建器。

与 /api/summary 使用同一 CNY 折算口径；数字由后端统一计算，缺失值显式标注，
不伪造。供 portfolio-review 投研使用。
"""
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlmodel import Session, select

from models import (
    Currency, FxRate, Holding, HoldingStatus, Note, Platform, User,
    cost_basis, market_value, profit, has_valuation,
)

HKD_PEG = 7.8


def get_to_cny_rates(session: Session) -> Tuple[Dict[Currency, float], float, str]:
    fx = session.exec(select(FxRate).where(FxRate.pair == "USDCNY")).first()
    usdcny = fx.rate if fx else 7.2
    fx_updated_at = fx.updated_at.isoformat() if fx and fx.updated_at else "unknown"
    to_cny = {
        Currency.CNY: 1.0,
        Currency.USD: usdcny,
        Currency.HKD: usdcny / HKD_PEG,
    }
    return to_cny, usdcny, fx_updated_at


def _valued(h: Holding) -> bool:
    """该持仓是否有可估值的市值（手填金额或 数量×现价）。"""
    return has_valuation(h)


def _fmt(v: Optional[float], cur: str, digits: int = 2) -> str:
    return "未知" if v is None else f"{v:,.{digits}f} {cur}"


def build_account_context(session: Session, user: User, display_currency: Currency, compact: bool = False) -> str:
    to_cny, usdcny, fx_updated_at = get_to_cny_rates(session)
    holdings = list(session.exec(select(Holding).where(Holding.user_id == user.id)).all())
    platforms = {
        p.id: p.name
        for p in session.exec(select(Platform).where(Platform.user_id == user.id)).all()
    }

    if not holdings:
        return "\n**（当前无任何账户或持仓数据）**\n"

    open_holdings = [h for h in holdings if h.status == HoldingStatus.open]
    closed_holdings = [h for h in holdings if h.status == HoldingStatus.closed]

    rows = []
    total_cny = 0.0
    cost_cny = 0.0
    unrealized_cny = 0.0
    realized_pnl_cny = 0.0
    realized_income_cny = 0.0
    for h in holdings:
        rate = to_cny.get(h.currency, 1.0)
        mv_native = market_value(h)
        cb = cost_basis(h)
        pnl = profit(h)
        mv_cny = mv_native * rate
        cb_cny = cb * rate if cb is not None else None
        pnl_cny = pnl * rate if pnl is not None else None
        if h.status == HoldingStatus.open and _valued(h):
            total_cny += mv_cny
            if cb_cny is not None:
                cost_cny += cb_cny
                unrealized_cny += (pnl_cny or 0.0)
        realized_pnl_cny += (h.realized_pnl or 0.0) * rate
        realized_income_cny += (h.realized_income or 0.0) * rate
        rows.append({
            "h": h, "rate": rate, "mv_native": mv_native, "mv_cny": mv_cny,
            "cb_cny": cb_cny, "pnl": pnl, "pnl_cny": pnl_cny,
        })

    def to_display(cny: float) -> float:
        rate = to_cny.get(display_currency, 1.0)
        return cny / rate if rate else 0.0

    cur_label = display_currency.value

    by_account = defaultdict(float)
    by_type = defaultdict(float)
    by_currency_native = defaultdict(float)
    cash_cny = 0.0
    for r in rows:
        h = r["h"]
        if h.status != HoldingStatus.open:
            continue
        by_account[h.platform_id] += r["mv_cny"]
        by_type[h.asset_type.value] += r["mv_cny"]
        by_currency_native[h.currency.value] += r["mv_native"]
        if h.asset_type.value == "cash":
            cash_cny += r["mv_cny"]

    groups = defaultdict(lambda: {"mv_cny": 0.0, "accounts": set(), "h": None})
    for r in rows:
        h = r["h"]
        if h.status != HoldingStatus.open:
            continue
        if h.symbol and h.market.value != "NONE":
            g = groups[(h.market.value, h.symbol)]
            g["mv_cny"] += r["mv_cny"]
            g["accounts"].add(platforms.get(h.platform_id, f"#{h.platform_id}"))
            g["h"] = g["h"] or h
    top_symbols = sorted(groups.values(), key=lambda g: g["mv_cny"], reverse=True)

    lines: List[str] = []
    lines.append("## 分析时点与展示口径")
    lines.append(f"- 分析时点：{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"- 展示币种：{cur_label}")
    lines.append(f"- USD/CNY = {usdcny:.4f}；HKD/CNY ≈ {usdcny / HKD_PEG:.4f}（联系汇率≈7.8 HKD/USD，估算）")
    lines.append(f"- 汇率更新时间：{fx_updated_at}")
    lines.append("- 汇率来源链：open.er-api.com，失败时回退中国银行；现有记录未保存实际命中来源。无汇率记录时使用 7.2 默认估算，不能视为实时汇率。")

    lines.append("")
    lines.append("## 账户汇总")
    lines.append(f"- 总资产：{_fmt(to_display(total_cny), cur_label)}")
    lines.append(f"- 现金：{_fmt(to_display(cash_cny), cur_label)}")
    lines.append(f"- 未实现盈亏：{_fmt(to_display(unrealized_cny), cur_label)}")
    lines.append(f"- 已实现盈亏：{_fmt(to_display(realized_pnl_cny), cur_label)}（含已清仓持仓）")
    lines.append(f"- 分红/利息：{_fmt(to_display(realized_income_cny), cur_label)}")
    if closed_holdings:
        lines.append(f"- 已清仓持仓数：{len(closed_holdings)}（其已实现盈亏已并入上表，不列为当前持仓）")

    lines.append("")
    lines.append("## 账户与配置")
    lines.append("### 各账户")
    for pid, cny in sorted(by_account.items(), key=lambda kv: kv[1], reverse=True):
        lines.append(f"- {platforms.get(pid, f'#{pid}')}：{_fmt(to_display(cny), cur_label)}")
    lines.append("### 资产类型")
    for t, cny in sorted(by_type.items(), key=lambda kv: kv[1], reverse=True):
        lines.append(f"- {t}：{_fmt(to_display(cny), cur_label)}")
    lines.append("### 币种分布（原币种口径）")
    for c, native in sorted(by_currency_native.items(), key=lambda kv: kv[1], reverse=True):
        lines.append(f"- {c}：{_fmt(native, c)}")
    lines.append("### 集中度（跨账户同标的合计）")
    if top_symbols:
        for g in top_symbols:
            h = g["h"]
            pct = (g["mv_cny"] / total_cny * 100) if total_cny else 0.0
            accts = "、".join(sorted(g["accounts"]))
            lines.append(
                f"- {h.name or h.symbol}（{h.market.value}:{h.symbol}）：约 {to_display(g['mv_cny']):,.0f} "
                f"{cur_label}，占 {pct:.1f}%（账户：{accts}）"
            )
    else:
        lines.append("- 无可用集中度数据")

    lines.append("")
    lines.append("## 持仓明细")
    lines.append("| 标的 | 市场 | 代码 | 账户 | 币种 | 数量 | 成本价 | 现价 | 市值 | 未实现盈亏 | 权重 | 行情获取时间(UTC) |")
    lines.append("|------|------|------|------|------|------|-------|------|------|-----------|----------|-------------------|")
    for r in rows:
        h = r["h"]
        if h.status != HoldingStatus.open:
            continue
        w = (r["mv_cny"] / total_cny * 100) if total_cny else 0.0
        acct = platforms.get(h.platform_id, f"#{h.platform_id}")
        qty = "缺失" if h.quantity is None else f"{h.quantity:g}"
        cpr = "缺失" if h.cost_price is None else f"{h.cost_price:g}"
        cur_p = f"{h.current_price:g}" if h.current_price is not None else ("手填" if h.manual_value is not None else "缺失")
        weight = f"{w:.1f}%" if _valued(h) else "未知"
        quote_time = h.price_updated_at.isoformat() if h.price_updated_at else "未知"
        mv_native = _fmt(r["mv_native"], h.currency.value, 0) if _valued(h) else "缺失"
        if not _valued(h):
            pnl_native = "未知（缺现价）"
        elif r["pnl"] is None:
            pnl_native = "未知（缺成本）"
        else:
            pnl_native = _fmt(r["pnl"], h.currency.value)
        lines.append(
            f"| {h.name or '—'} | {h.market.value} | {h.symbol or '—'} | {acct} | {h.currency.value} "
            f"| {qty} | {cpr} | {cur_p} | {mv_native} | {pnl_native} | {weight} | {quote_time} |"
        )

    notes = session.exec(
        select(Note).where(
            Note.user_id == user.id,
            Note.note_type.in_(["thesis", "risk", "review", "observation"]),
        ).order_by(Note.updated_at.desc()).limit(3 if compact else 20)
    ).all()
    lines.append("")
    lines.append("## 相关投资逻辑与风险笔记")
    if notes:
        for n in notes:
            tag = n.symbol or (n.title or "")[:30]
            body = (n.content or "").strip().replace("\n", " ")
            lines.append(f"- [{n.note_type}] {tag}：{body[:100 if compact else 200]}")
        lines.append("- 笔记仅摘录最近相关记录；全部持仓明细均保留。")
    else:
        lines.append("- （无）")

    stale = sum(1 for h in open_holdings if h.manual_value is None and
                (h.price_updated_at is None or datetime.utcnow() - h.price_updated_at > timedelta(hours=24)))
    lines.append(f"- 行情过期或获取时间未知：{stale} 项；获取时间不等同于交易所报价时点。过期数据只能用于暂估，不给出精确调仓金额。")
    priced = sum(1 for h in open_holdings if _valued(h))
    lines.append("")
    lines.append("## 数据质量与口径说明")
    lines.append(
        f"- 估值覆盖：{priced}/{len(open_holdings)} 个未清仓持仓有行情或手填金额；"
        "缺失的市值/成本已显式标注「缺失」或「未知」，不代表其值为 0。"
    )
    lines.append("- 现金口径：现金账本主要由入金/出金流水重算，未完整联动证券买卖，故不可视为精确可用余额，也不据此给出精确调仓金额。")
    lines.append("- HKD 通过 7.8 HKD/USD 近似折算，为估算值。")
    lines.append("- 数字由后台统一折算为 CNY 后再换算展示币种，与总览同口径。")

    return "\n".join(lines)
