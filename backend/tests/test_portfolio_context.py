"""全账户组合上下文构建测试。"""
from datetime import datetime

from models import Currency, FxRate, Holding, Platform, User


def _mk(session, user, currency="CNY", market="A", symbol="600519", name="茅台",
         quantity=100.0, cost_price=100.0, current_price=100.0, status="open",
         realized_pnl=0.0, realized_income=0.0, platform=None):
    if platform is None:
        platform = Platform(user_id=user.id, name="默认平台")
        session.add(platform)
        session.commit()
        session.refresh(platform)
    h = Holding(
        user_id=user.id, platform_id=platform.id, currency=currency, market=market,
        symbol=symbol, name=name, quantity=quantity, cost_price=cost_price,
        current_price=current_price, status=status, realized_pnl=realized_pnl,
        realized_income=realized_income,
    )
    session.add(h)
    session.commit()
    session.refresh(h)
    return h, platform


def test_total_matches_summary_cny(client, session, user):
    """多币种总资产应与 /api/summary 的 CNY 口径一致。"""
    session.add(FxRate(pair="USDCNY", rate=7.0, updated_at=datetime.utcnow()))
    session.commit()
    _mk(session, user, currency="CNY", quantity=100, current_price=100)  # 10,000 CNY
    _mk(session, user, currency="USD", market="US", symbol="AAPL", name="Apple",
        quantity=100, current_price=100)  # 10,000 USD -> 70,000 CNY

    from portfolio_context import build_account_context
    ctx = build_account_context(session, user, Currency.CNY)
    assert "80,000" in ctx  # 10,000 + 70,000
    assert "展示币种：CNY" in ctx


def test_display_currency_usd(client, session, user):
    session.add(FxRate(pair="USDCNY", rate=7.0, updated_at=datetime.utcnow()))
    session.commit()
    _mk(session, user, currency="USD", market="US", symbol="AAPL", name="Apple",
        quantity=100, current_price=100)  # 10,000 USD

    from portfolio_context import build_account_context
    ctx = build_account_context(session, user, Currency.USD)
    assert "展示币种：USD" in ctx
    assert "10,000" in ctx  # 展示币种为 USD 时总资产≈10,000


def test_cross_account_same_symbol_merged(client, session, user):
    p1 = Platform(user_id=user.id, name="券商A"); session.add(p1); session.commit(); session.refresh(p1)
    p2 = Platform(user_id=user.id, name="券商B"); session.add(p2); session.commit(); session.refresh(p2)
    _mk(session, user, market="US", symbol="AAPL", name="Apple", quantity=10, current_price=100, platform=p1)
    _mk(session, user, market="US", symbol="AAPL", name="Apple", quantity=20, current_price=100, platform=p2)

    from portfolio_context import build_account_context
    ctx = build_account_context(session, user, Currency.CNY)
    assert "券商A" in ctx and "券商B" in ctx  # 保留账户明细
    assert "AAPL" in ctx  # 集中度合并后仍含该标的


def test_different_market_same_symbol_not_merged(client, session, user):
    _mk(session, user, market="A", symbol="0700", name="A股0700", quantity=10, current_price=10)
    _mk(session, user, market="HK", symbol="0700", name="腾讯", quantity=10, current_price=10)
    from portfolio_context import build_account_context
    ctx = build_account_context(session, user, Currency.CNY)
    assert "A股0700" in ctx and "腾讯" in ctx  # 两者都保留，未误合并


def test_closed_holding_realized_pnl_included(client, session, user):
    _mk(session, user, status="open", quantity=10, current_price=10)
    _mk(session, user, status="closed", symbol="CLOSED", name="已清仓",
        quantity=0, current_price=None, realized_pnl=500.0)
    from portfolio_context import build_account_context
    ctx = build_account_context(session, user, Currency.CNY)
    assert "已清仓" in ctx or "已清仓持仓" in ctx
    assert "500.00" in ctx  # 已实现盈亏含清仓收益


def test_missing_price_marked_not_zero(client, session, user):
    _mk(session, user, quantity=10, cost_price=50, current_price=None)  # 缺现价
    from portfolio_context import build_account_context
    ctx = build_account_context(session, user, Currency.CNY)
    assert "缺失" in ctx  # 现价/市值显式标注为缺失
    assert "未知（缺现价）" in ctx  # 盈亏不解释为 0 或 -100%


def test_missing_cost_marked_not_zero(client, session, user):
    _mk(session, user, quantity=10, cost_price=None, current_price=100)  # 缺成本价
    from portfolio_context import build_account_context
    ctx = build_account_context(session, user, Currency.CNY)
    assert "未知（缺成本）" in ctx  # 有现价但缺成本时标注


def test_cash_and_hkd_disclaimers(client, session, user):
    session.add(FxRate(pair="USDCNY", rate=7.0, updated_at=datetime.utcnow()))
    session.commit()
    _mk(session, user, currency="HKD", market="HK", symbol="0700", name="腾讯",
        quantity=100, current_price=100)
    from portfolio_context import build_account_context
    ctx = build_account_context(session, user, Currency.CNY)
    assert "7.8" in ctx  # HKD 近似折算标注
    assert "入金" in ctx or "现金" in ctx  # 现金口径说明


def test_missing_price_not_counted_as_aggregate_loss(client, session, user):
    _mk(session, user, quantity=10, cost_price=50, current_price=None)  # 缺现价：成本 500
    _mk(session, user, market="US", symbol="AAPL", name="Apple", quantity=10, current_price=100)
    from portfolio_context import build_account_context
    ctx = build_account_context(session, user, Currency.CNY)
    assert "未知（缺现价）" in ctx  # 明细中显式标注
    assert "-500" not in ctx  # 缺价持仓不并入汇总，避免误报 -100% 亏损


def test_hkd_display_currency(client, session, user):
    session.add(FxRate(pair="USDCNY", rate=7.8, updated_at=datetime.utcnow()))
    session.commit()
    _mk(session, user, currency="HKD", market="HK", symbol="0700", name="腾讯",
        quantity=100, current_price=100)  # 10,000 HKD
    from portfolio_context import build_account_context
    ctx = build_account_context(session, user, Currency.HKD)
    assert "展示币种：HKD" in ctx
    assert "10,000" in ctx  # 展示币种为 HKD 时总资产≈10,000 HKD
