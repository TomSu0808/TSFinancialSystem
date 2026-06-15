from models import Transaction, TxnAction
from position import replay_transactions


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
