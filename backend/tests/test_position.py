from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool
from models import Holding, HoldingSource, HoldingStatus, Platform, User
from models import Transaction, TxnAction
from position import replay_transactions, recompute_holding


def _mem_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _buy(date, q, price, fee=0.0):
    return Transaction(id=None, date=date, action=TxnAction.buy, quantity=q, price=price, fee=fee)


def _sell(date, q, price, fee=0.0):
    return Transaction(id=None, date=date, action=TxnAction.sell, quantity=q, price=price, fee=fee)


def test_weighted_average_on_multiple_buys():
    st = replay_transactions([_buy("2026-01-01", 100, 10), _buy("2026-01-02", 100, 20)])
    assert st.quantity == 200
    assert st.avg_cost == 15.0
    assert st.realized_pnl == 0.0


def test_partial_sell_realizes_pnl_and_keeps_avg_cost():
    st = replay_transactions([_buy("2026-01-01", 200, 15), _sell("2026-02-01", 100, 25)])
    assert st.quantity == 100
    assert st.avg_cost == 15.0
    assert st.realized_pnl == 100 * (25 - 15)


def test_full_sell_closes_position():
    st = replay_transactions([_buy("2026-01-01", 100, 10), _sell("2026-02-01", 100, 12)])
    assert st.quantity == 0.0
    assert st.avg_cost == 0.0
    assert st.realized_pnl == 100 * (12 - 10)


def test_fee_added_on_buy_subtracted_on_sell():
    st = replay_transactions([_buy("2026-01-01", 100, 10, fee=5), _sell("2026-02-01", 50, 10, fee=3)])
    assert round(st.avg_cost, 4) == 10.05
    assert round(st.realized_pnl, 4) == round(50 * 10 - 50 * 10.05 - 3, 4)


def test_dividend_counts_as_income_only():
    div = Transaction(id=None, date="2026-03-01", action=TxnAction.dividend, amount=88.0)
    st = replay_transactions([_buy("2026-01-01", 100, 10), div])
    assert st.quantity == 100
    assert st.avg_cost == 10.0
    assert st.realized_income == 88.0


def test_oversell_yields_negative_quantity_anomaly():
    st = replay_transactions([_buy("2026-01-01", 100, 10), _sell("2026-02-01", 150, 12)])
    assert st.quantity < 0


def test_recompute_writes_back_and_closes():
    s = _mem_session()
    u = User(username="t", password_hash="x"); s.add(u); s.commit(); s.refresh(u)
    p = Platform(user_id=u.id, name="P"); s.add(p); s.commit(); s.refresh(p)
    h = Holding(user_id=u.id, platform_id=p.id, symbol="AAPL", source=HoldingSource.derived)
    s.add(h); s.commit(); s.refresh(h)
    s.add(Transaction(user_id=u.id, platform_id=p.id, holding_id=h.id,
                      date="2026-01-01", action=TxnAction.buy, quantity=100, price=10))
    s.add(Transaction(user_id=u.id, platform_id=p.id, holding_id=h.id,
                      date="2026-02-01", action=TxnAction.sell, quantity=100, price=12))
    s.commit()

    recompute_holding(s, h.id)
    s.refresh(h)
    assert h.quantity == 0.0
    assert h.status == HoldingStatus.closed
    assert h.realized_pnl == 200.0


def test_recompute_ignores_manual_holding():
    s = _mem_session()
    u = User(username="t", password_hash="x"); s.add(u); s.commit(); s.refresh(u)
    p = Platform(user_id=u.id, name="P"); s.add(p); s.commit(); s.refresh(p)
    h = Holding(user_id=u.id, platform_id=p.id, quantity=5, cost_price=3,
                source=HoldingSource.manual)
    s.add(h); s.commit(); s.refresh(h)
    recompute_holding(s, h.id)
    s.refresh(h)
    assert h.quantity == 5
    assert h.cost_price == 3


# ── Decimal 精度测试 ──────────────────────────────────────────────────

def test_decimal_0_1_plus_0_2():
    """验证 Decimal 计算 0.1 + 0.2 的精度（对比 float）。"""
    from decimal_utils import to_d, to_float, d_sum

    # float 的经典问题
    assert 0.1 + 0.2 != 0.3  # float: 0.30000000000000004

    # Decimal 精确
    result = d_sum(0.1, 0.2)
    assert result == to_d("0.3")
    assert to_float(result, ndigits=10) == 0.3


def test_replay_transactions_decimal_precision():
    """交易回放使用 Decimal，避免浮点累积误差。"""
    txns = [
        _buy("2026-01-01", 0.1, 10.0),
        _buy("2026-01-02", 0.2, 10.0),
        _buy("2026-01-03", 0.3, 10.0),
    ]
    st = replay_transactions(txns)
    # 精确结果应为 0.6，不会出现 0.6000000000000001
    assert st.quantity == 0.6
    assert st.avg_cost == 10.0


def test_fractional_shares_cost_precision():
    """分批买卖小数量时的成本精度。"""
    txns = [
        _buy("2026-01-01", 1.0 / 3.0, 150.0),   # 0.333... 股
        _buy("2026-01-02", 1.0 / 3.0, 155.0),
        _buy("2026-01-03", 1.0 / 3.0, 160.0),
    ]
    st = replay_transactions(txns)
    assert abs(st.quantity - 1.0) < 1e-9  # ~1 股
    assert abs(st.avg_cost - 155.0) < 1e-9  # 平均成本 ~155


def test_fee_subtraction_precision():
    """费用扣减精度（避免 0.05000000000001 之类）。"""
    txns = [
        _buy("2026-01-01", 100, 10.0, fee=5.15),
    ]
    st = replay_transactions(txns)
    # 成本 = (100 * 10 + 5.15) / 100 = 10.0515
    assert abs(st.avg_cost - 10.0515) < 1e-9


def test_realized_pnl_fractional():
    """小额已实现盈亏应精确。"""
    txns = [
        _buy("2026-01-01", 10, 100.0),
        _sell("2026-02-01", 3, 100.5, fee=1.23),
    ]
    st = replay_transactions(txns)
    # realized_pnl = 3*100.5 - 3*100 - 1.23 = 301.5 - 300.0 - 1.23 = 0.27
    assert abs(st.realized_pnl - 0.27) < 1e-9


def test_market_value_decimal():
    """market_value 使用 Decimal 避免浮点误差。"""
    from models import market_value
    from decimal_utils import to_float, d_mul

    h = Holding(quantity=0.1, current_price=0.2)
    mv = market_value(h)
    # 0.1 * 0.2 = 0.02（float 可能产生 0.020000000000000004）
    assert abs(mv - 0.02) < 1e-10
    assert to_float(d_mul(0.1, 0.2)) == 0.02


def test_profit_decimal():
    """profit 计算使用 Decimal。"""
    from models import profit
    h = Holding(
        quantity=100.0,
        cost_price=10.0,
        current_price=10.5,
    )
    p = profit(h)
    # profit = 100 * 10.5 - 100 * 10 = 50
    assert p is not None
    assert abs(p - 50.0) < 1e-9


def test_day_change_decimal():
    """day_change 使用 Decimal。"""
    from models import day_change
    h = Holding(
        quantity=100.0,
        current_price=10.5,
        prev_close=10.0,
    )
    dc = day_change(h)
    # day_change = 100 * (10.5 - 10.0) = 50
    assert abs(dc - 50.0) < 1e-9
