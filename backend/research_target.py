"""研究标的解析与 TradingAgents 输入适配。

关键约束：
- 不猜测同名/同代码标的；歧义时要求用户明确选择持仓。
- TradingAgents 的组合输入只有单一币种，因此只携带与分析标的同币种的
  持仓和现金，并对被排除的其他币种做显式说明。
- 不支持的资产类型在提交前明确拒绝。
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from sqlmodel import Session, select

from models import (
    AssetType, Currency, Holding, HoldingStatus, Market, User,
    cost_basis, market_value,
)


SUPPORTED_TA_MARKETS = {"US", "HK", "A", "CRYPTO"}
SUPPORTED_TA_ASSETS = {"stock", "etf", "crypto"}


def _enum_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value or "")


def resolve_target(
    session: Session,
    user: User,
    target_name: Optional[str],
    symbol: Optional[str],
    market: Optional[str],
    related_holding_id: Optional[int],
) -> Dict[str, Any]:
    holding: Optional[Holding] = None
    if related_holding_id is not None:
        holding = session.get(Holding, related_holding_id)
        if not holding or holding.user_id != user.id:
            raise PermissionError("持仓不存在或不属于当前用户")

    wanted_symbol = (symbol or "").strip()
    wanted_market = (market or "").strip().upper()
    wanted_name = (target_name or "").strip()

    if holding is not None:
        holding_symbol = (holding.symbol or "").strip()
        holding_market = _enum_value(holding.market).upper()
        if wanted_symbol and holding_symbol and wanted_symbol.upper() != holding_symbol.upper():
            raise ValueError("所选持仓的代码与填写代码不一致，请重新选择持仓或清空代码")
        if wanted_market and holding_market and wanted_market != holding_market:
            raise ValueError("所选持仓的市场与填写市场不一致，请重新选择")
        return {
            "holding": holding,
            "target_name": holding.name or holding_symbol or wanted_name,
            "symbol": holding_symbol or wanted_symbol,
            "market": holding_market or wanted_market,
            "currency": _enum_value(holding.currency),
            "asset_type": _enum_value(holding.asset_type),
            "identity_source": "holding",
            "warnings": [],
        }

    holdings = list(session.exec(
        select(Holding).where(Holding.user_id == user.id)
    ).all())

    if wanted_symbol:
        matches = [h for h in holdings if (h.symbol or "").upper() == wanted_symbol.upper()]
        if wanted_market:
            matches = [h for h in matches if _enum_value(h.market).upper() == wanted_market]
        identities = {(_enum_value(h.market), (h.symbol or "").upper(), _enum_value(h.currency)) for h in matches}
        if len(matches) > 1 or len(identities) > 1:
            raise ValueError(
                "该代码对应用户的多个持仓/市场，无法自动确定研究标的；"
                "请在上方选择一个具体持仓后再提交。"
            )
        if len(matches) == 1:
            h = matches[0]
            return {
                "holding": h,
                "target_name": wanted_name or h.name,
                "symbol": h.symbol or wanted_symbol,
                "market": _enum_value(h.market) or wanted_market,
                "currency": _enum_value(h.currency),
                "asset_type": _enum_value(h.asset_type),
                "identity_source": "holding_by_symbol",
                "warnings": ["已根据代码匹配到唯一持仓，并携带该持仓上下文。"],
            }

    if wanted_name:
        name_matches = [h for h in holdings if (h.name or "").strip() == wanted_name]
        if wanted_market:
            name_matches = [h for h in name_matches if _enum_value(h.market).upper() == wanted_market]
        distinct = {(_enum_value(h.market), (h.symbol or "").upper(), _enum_value(h.currency)) for h in name_matches}
        if len(distinct) > 1:
            raise ValueError(
                "公司名称匹配到多个不同市场/代码的持仓，请选择具体持仓或填写代码，"
                "系统不会猜测研究标的。"
            )
        if len(name_matches) > 1:
            raise ValueError("公司名称对应多个账户持仓，请选择一个具体持仓后再提交。")

    if not wanted_name and not wanted_symbol:
        raise ValueError("请选择研究对象：已有持仓或经身份确认的公司/证券")

    currency = "USD" if wanted_market == "US" else "HKD" if wanted_market == "HK" else "CNY"
    return {
        "holding": None,
        "target_name": wanted_name or wanted_symbol,
        "symbol": wanted_symbol,
        "market": wanted_market,
        "currency": currency,
        "asset_type": "crypto" if wanted_market == "CRYPTO" else "stock",
        "identity_source": "manual",
        "warnings": [] if wanted_market else ["未指定市场；报告无法保证标的身份唯一。"],
    }


def to_yahoo_ticker(symbol: str, market: str, asset_type: str = "stock") -> str:
    raw = (symbol or "").strip().upper()
    if not raw:
        raise ValueError("多 Agent 研究需要明确的证券代码")
    market = (market or "").upper()
    if asset_type == "crypto":
        if raw.endswith("-USD") or "-" in raw:
            return raw
        return raw + "-USD"
    if market == "HK":
        if raw.endswith(".HK"):
            return raw
        digits = re.sub(r"\D", "", raw)
        return (digits.zfill(4) if digits else raw) + ".HK"
    if market == "A":
        if raw.endswith(".SS") or raw.endswith(".SZ"):
            return raw
        digits = re.sub(r"\D", "", raw)
        if digits.startswith(("6", "9")):
            return digits + ".SS"
        if digits.startswith(("0", "3")):
            return digits + ".SZ"
        raise ValueError("A 股代码需以 6/9（沪市）或 0/3（深市）开头，无法安全映射到 Yahoo 代码")
    if market == "US":
        return raw
    raise ValueError(f"多 Agent 研究暂不支持市场 {market or '未指定'}")


def multi_agent_support(
    asset_type: str,
    market: str,
    symbol: str,
) -> Tuple[bool, str]:
    if asset_type not in SUPPORTED_TA_ASSETS:
        return False, (
            f"多 Agent 研究暂不支持资产类型 {asset_type}；"
            "请使用标准研究，或改为受支持的股票/ETF/加密资产。"
        )
    if market not in SUPPORTED_TA_MARKETS:
        return False, f"多 Agent 研究暂不支持市场 {market or '未指定'}；请使用标准研究。"
    if not symbol:
        return False, "多 Agent 研究需要明确的证券代码；仅凭公司名称无法安全映射行情标识。"
    return True, ""


def build_ta_portfolio(
    session: Session,
    user: User,
    target: Dict[str, Any],
) -> Dict[str, Any]:
    """构造单币种组合输入；明确列出被排除的其他币种持仓。"""
    currency = target.get("currency") or "USD"
    holdings = list(session.exec(
        select(Holding).where(
            Holding.user_id == user.id,
            Holding.status == HoldingStatus.open,
        )
    ).all())
    included = []
    excluded = []
    cash = 0.0
    for h in holdings:
        if _enum_value(h.currency) != currency:
            excluded.append(h)
            continue
        if _enum_value(h.asset_type) == "cash":
            value = market_value(h)
            if value:
                cash += value
            continue
        if _enum_value(h.asset_type) not in SUPPORTED_TA_ASSETS:
            excluded.append(h)
            continue
        try:
            ticker = to_yahoo_ticker(
                h.symbol, _enum_value(h.market), _enum_value(h.asset_type))
        except ValueError:
            excluded.append(h)
            continue
        quantity = h.quantity if h.quantity is not None else 0
        included.append({
            "ticker": ticker,
            "quantity": float(quantity or 0),
            "average_price": h.cost_price,
            "asset_type": _enum_value(h.asset_type),
            "name": h.name,
        })
    target_ticker = to_yahoo_ticker(
        target.get("symbol") or "",
        target.get("market") or "",
        target.get("asset_type") or "stock",
    )
    return {
        "portfolio": {
            "cash": round(cash, 2) if cash else None,
            "currency": currency,
            "positions": included,
        },
        "target_ticker": target_ticker,
        "excluded_holdings": [
            {
                "name": h.name,
                "symbol": h.symbol,
                "market": _enum_value(h.market),
                "currency": _enum_value(h.currency),
                "reason": "不同币种或该资产类型不适用于 TradingAgents 单币种输入",
            }
            for h in excluded
        ],
        "currency": currency,
        "limitations": [
            f"仅携带 {currency} 计价的持仓与现金；其他币种持仓未被转换或混入。",
            "TradingAgents 的组合输入不支持多币种，本系统未用汇率伪造跨币种平均成本。",
        ] if excluded or len({_enum_value(h.currency) for h in holdings}) > 1 else [
            "组合输入仅包含同一币种的持仓与现金。",
        ],
    }


def preview_holdings_summary(session: Session, user: User) -> Dict[str, Any]:
    holdings = list(session.exec(
        select(Holding).where(Holding.user_id == user.id, Holding.status != HoldingStatus.closed)
    ).all())
    missing_price = [h for h in holdings if _enum_value(h.asset_type) != "cash" and market_value(h) <= 0]
    missing_cost = [h for h in holdings if cost_basis(h) is None]
    currencies = sorted({_enum_value(h.currency) for h in holdings})
    return {
        "holding_count": len(holdings),
        "currencies": currencies,
        "missing_price_count": len(missing_price),
        "missing_cost_count": len(missing_cost),
        "missing_price_names": [h.name or h.symbol or f"#{h.id}" for h in missing_price[:8]],
        "missing_cost_names": [h.name or h.symbol or f"#{h.id}" for h in missing_cost[:8]],
    }
