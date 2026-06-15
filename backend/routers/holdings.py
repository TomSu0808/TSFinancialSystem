"""资产持仓增删改查 + 一键刷新行情（按登录用户隔离）。"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from auth import get_current_user
from database import get_session
from models import (
    Currency, Holding, HoldingCreate, HoldingSource, HoldingStatus,
    HoldingUpdate, Platform, User,
)
from price_provider import fetch_quote

router = APIRouter(prefix="/api/holdings", tags=["holdings"])


def _check_platform(session: Session, platform_id: int, user: User) -> None:
    """确认目标平台属于当前用户，否则 404。"""
    platform = session.get(Platform, platform_id)
    if not platform or platform.user_id != user.id:
        raise HTTPException(404, "平台不存在")


def _owned(session: Session, holding_id: int, user: User) -> Holding:
    holding = session.get(Holding, holding_id)
    if not holding or holding.user_id != user.id:
        raise HTTPException(404, "资产不存在")
    return holding


@router.get("", response_model=List[Holding])
def list_holdings(
    platform_id: Optional[int] = Query(None),
    currency: Optional[Currency] = Query(None),
    include_closed: bool = Query(False),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    stmt = select(Holding).where(Holding.user_id == user.id)
    if platform_id is not None:
        stmt = stmt.where(Holding.platform_id == platform_id)
    if currency is not None:
        stmt = stmt.where(Holding.currency == currency)
    if not include_closed:
        stmt = stmt.where(Holding.status != HoldingStatus.closed)
    return session.exec(stmt).all()


@router.post("", response_model=Holding)
def create_holding(
    data: HoldingCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    _check_platform(session, data.platform_id, user)
    holding = Holding.model_validate(data, update={"user_id": user.id})
    session.add(holding)
    session.commit()
    session.refresh(holding)
    return holding


@router.put("/{holding_id}", response_model=Holding)
def update_holding(
    holding_id: int,
    data: HoldingUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    holding = _owned(session, holding_id, user)
    values = data.model_dump(exclude_unset=True)
    if holding.source == HoldingSource.derived and (
        "quantity" in values or "cost_price" in values
    ):
        raise HTTPException(400, "该持仓由交易流水驱动，请通过交易记录修改数量/成本")
    if "platform_id" in values:
        _check_platform(session, values["platform_id"], user)
    for key, value in values.items():
        setattr(holding, key, value)
    session.add(holding)
    session.commit()
    session.refresh(holding)
    return holding


@router.delete("/{holding_id}")
def delete_holding(
    holding_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    holding = _owned(session, holding_id, user)
    session.delete(holding)
    session.commit()
    return {"ok": True}


@router.post("/refresh-prices")
def refresh_prices(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """一键更新行情：遍历当前用户的可抓价持仓，逐条拉最新价/昨收并写回。

    单条失败不影响其它，返回每条的成功/失败状态。
    """
    holdings = session.exec(
        select(Holding).where(Holding.user_id == user.id)
    ).all()
    results = []
    for h in holdings:
        # 手填金额的资产跳过抓价
        if h.manual_value is not None or not h.symbol:
            results.append({"id": h.id, "symbol": h.symbol, "status": "skipped"})
            continue
        try:
            quote = fetch_quote(h.market, h.symbol)
            if quote and quote.get("price") is not None:
                h.current_price = quote["price"]
                h.prev_close = quote.get("prev_close")
                h.price_updated_at = datetime.utcnow()
                session.add(h)
                results.append(
                    {"id": h.id, "symbol": h.symbol, "status": "ok",
                     "price": h.current_price}
                )
            else:
                results.append(
                    {"id": h.id, "symbol": h.symbol, "status": "not_found"}
                )
        except Exception as e:  # noqa: BLE001 — 单条失败不应中断整体刷新
            results.append(
                {"id": h.id, "symbol": h.symbol, "status": "error", "detail": str(e)}
            )
    session.commit()
    ok = sum(1 for r in results if r["status"] == "ok")
    return {"updated": ok, "total": len(results), "results": results}
