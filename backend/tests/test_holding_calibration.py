import pytest


def setup_position(client, **values):
    pid = client.post('/api/platforms', json={'name': 'Calibration'}).json()['id']
    base = {'platform_id': pid, 'symbol': 'AAPL', 'name': 'Apple', 'currency': 'USD'}
    base.update({k: v for k, v in values.items() if k in base})
    h = client.post('/api/holdings', json={**base, 'quantity': 100, 'cost_price': 10, **values})
    assert h.status_code == 200
    return base, h.json()


def holdings(client):
    return client.get('/api/holdings?include_closed=true').json()


def transaction(client, base, action, quantity, **values):
    return client.post('/api/transactions', json={
        **base, 'date': '2026-09-01', 'action': action, 'quantity': quantity,
        'price': 12, **values,
    })


def test_manual_holding_sell_without_buy_and_undo(client):
    base, original = setup_position(client)
    sold = transaction(client, base, 'sell', 20)
    assert sold.status_code == 200, sold.text
    h, = holdings(client)
    assert h['id'] == original['id']
    assert h['quantity'] == 80
    assert h['cost_price'] == 10
    assert h['realized_pnl'] == 40
    txns = client.get('/api/transactions').json()
    assert sorted(t['action'] for t in txns) == ['adjust', 'sell']
    assert client.delete(f"/api/transactions/{sold.json()['id']}").status_code == 200
    assert holdings(client)[0]['quantity'] == 100


def test_calibrate_then_sell_and_preserve_previous_profit(client):
    base, _ = setup_position(client)
    assert transaction(client, base, 'sell', 20).status_code == 200
    adjusted = transaction(client, base, 'adjust', 150, date='2026-09-02', price=11)
    assert adjusted.status_code == 200, adjusted.text
    assert holdings(client)[0]['quantity'] == 150
    assert transaction(client, base, 'sell', 150, date='2026-09-03', price=13).status_code == 200
    h, = holdings(client)
    assert h['quantity'] == 0
    assert h['status'] == 'closed'
    assert h['realized_pnl'] == 340


def test_unknown_cost_not_counted_as_profit_and_can_be_repaired(client):
    base, _ = setup_position(client, cost_price=None)
    assert transaction(client, base, 'sell', 100).status_code == 200
    h, = holdings(client)
    assert h['realized_pnl'] == 0
    assert h['realized_pnl_incomplete'] is True
    opening = next(t for t in client.get('/api/transactions').json() if t['action'] == 'adjust')
    assert client.put(f"/api/transactions/{opening['id']}", json={'price': 10}).status_code == 200
    h, = holdings(client)
    assert h['realized_pnl'] == 200
    assert h['realized_pnl_incomplete'] is False


def test_manual_total_cost_is_used_and_cleared_on_conversion(client):
    base, _ = setup_position(client, cost_value=800, cost_price=10)
    assert transaction(client, base, 'sell', 20).status_code == 200
    h, = holdings(client)
    assert h['cost_price'] == 8
    assert h['cost_value'] is None
    assert h['realized_pnl'] == 80


def test_rejected_manual_oversell_does_not_convert_or_create_records(client):
    base, _ = setup_position(client)
    assert transaction(client, base, 'sell', 101).status_code == 400
    assert holdings(client)[0]['source'] == 'manual'
    assert client.get('/api/transactions').json() == []


def test_calibration_opens_position_without_buy_and_backup_roundtrip(client):
    pid = client.post('/api/platforms', json={'name': 'New'}).json()['id']
    base = {'platform_id': pid, 'symbol': 'MSFT', 'currency': 'USD'}
    assert transaction(client, base, 'adjust', 50, price=10).status_code == 200
    assert transaction(client, base, 'sell', 10).status_code == 200
    backup = client.get('/api/backup').json()
    assert client.post('/api/backup/import', json=backup).status_code == 200
    h, = holdings(client)
    assert h['quantity'] == 40
    assert h['realized_pnl'] == 20


def test_calibration_quantity_is_absolute_and_zero_is_allowed(client):
    base, _ = setup_position(client)
    assert transaction(client, base, 'adjust', 130).status_code == 200
    assert holdings(client)[0]['quantity'] == 130
    assert transaction(client, base, 'adjust', 0).status_code == 200
    assert holdings(client)[0]['status'] == 'closed'


@pytest.mark.parametrize('values', [{'quantity': -1}, {'price': -1}, {'fee': 2}, {'amount': 20}, {'symbol': ''}])
def test_invalid_calibration_rejected(client, values):
    base, _ = setup_position(client)
    payload = {**base, 'action': 'adjust', 'date': '2026-09-01', 'quantity': 10, **values}
    assert client.post('/api/transactions', json=payload).status_code == 400
    assert holdings(client)[0]['quantity'] == 100


def test_future_calibration_does_not_allow_earlier_oversell(client):
    base, _ = setup_position(client)
    assert transaction(client, base, 'adjust', 200, date='2026-09-10').status_code == 200
    assert transaction(client, base, 'sell', 150, date='2026-09-05').status_code == 400


def test_removing_or_reducing_opening_that_causes_oversell_rejected(client):
    base, _ = setup_position(client)
    assert transaction(client, base, 'sell', 50).status_code == 200
    opening = next(t for t in client.get('/api/transactions').json() if t['action'] == 'adjust')
    assert client.put(f"/api/transactions/{opening['id']}", json={'quantity': 40}).status_code == 400
    assert client.delete(f"/api/transactions/{opening['id']}").status_code == 400
    assert holdings(client)[0]['quantity'] == 50


def test_buy_after_manual_position_uses_existing_quantity(client):
    base, original = setup_position(client)
    assert transaction(client, base, 'buy', 100, price=20).status_code == 200
    h, = holdings(client)
    assert h['id'] == original['id']
    assert h['quantity'] == 200
    assert h['cost_price'] == 15


def test_ambiguous_manual_positions_rejected_without_changes(client):
    base, _ = setup_position(client)
    client.post('/api/holdings', json={**base, 'quantity': 30, 'cost_price': 10})
    assert transaction(client, base, 'sell', 20).status_code == 400
    assert sorted(h['quantity'] for h in holdings(client)) == [30, 100]
    assert client.get('/api/transactions').json() == []


def test_csv_manual_sell_preview_and_commit_agree(client):
    setup_position(client)
    content = 'date,action,name,symbol,platform,currency,quantity,price\n2026-09-01,sell,Apple,AAPL,Calibration,USD,20,12'
    files = {'file': ('sell.csv', content.encode(), 'text/csv')}
    preview = client.post('/api/transactions/import/preview', files=files)
    assert preview.status_code == 200
    assert preview.json()['error_rows'] == 0
    assert client.post('/api/transactions/import/commit', files=files).status_code == 200
    assert holdings(client)[0]['quantity'] == 80


def test_csv_calibration_resets_available_quantity(client):
    setup_position(client)
    content = ('date,action,name,symbol,platform,currency,quantity,price\n'
               '2026-09-01,adjust,Apple,AAPL,Calibration,USD,120,10\n'
               '2026-09-01,sell,Apple,AAPL,Calibration,USD,110,12')
    files = {'file': ('adjust.csv', content.encode(), 'text/csv')}
    preview = client.post('/api/transactions/import/preview', files=files)
    assert preview.json()['error_rows'] == 0
    assert client.post('/api/transactions/import/commit', files=files).status_code == 200
    assert holdings(client)[0]['quantity'] == 10


def test_missing_cost_summary_is_marked_incomplete(client):
    base, _ = setup_position(client, cost_price=None)
    assert transaction(client, base, 'sell', 100).status_code == 200
    summary = client.get('/api/summary?currency=USD').json()
    assert summary['realized_pnl'] == 0
    assert summary['returns_incomplete'] is True


def test_adjustment_cannot_use_other_users_holding(client, session):
    from models import User, Platform, Holding
    other = User(username='other-calibration', password_hash='x')
    session.add(other)
    session.flush()
    platform = Platform(user_id=other.id, name='Private')
    session.add(platform)
    session.flush()
    h = Holding(user_id=other.id, platform_id=platform.id, symbol='AAPL', quantity=100)
    session.add(h)
    session.commit()
    response = transaction(client, {'platform_id': platform.id, 'symbol': 'AAPL'}, 'adjust', 200)
    assert response.status_code == 404
    session.refresh(h)
    assert h.quantity == 100


def test_broker_import_can_sell_manual_holding(client):
    base, _ = setup_position(client)
    content = 'date,action,name,symbol,currency,quantity,price\n2026-09-01,sell,Apple,AAPL,USD,20,12'
    preview = client.post('/api/imports/preview',
                          data={'broker_type': 'generic', 'platform_id': base['platform_id']},
                          files={'file': ('sell.csv', content.encode(), 'text/csv')})
    assert preview.status_code == 200
    assert preview.json()['summary']['error'] == 0, preview.json()
    committed = client.post(f"/api/imports/{preview.json()['import_session_id']}/commit")
    assert committed.json()['created_count'] == 1
    assert holdings(client)[0]['quantity'] == 80


def test_calibration_rebases_daily_profit_instead_of_creating_income(client, session, user):
    from datetime import datetime
    from models import Holding
    from daily_pnl_service import record_daily_pnl
    base, _ = setup_position(client, currency='CNY')
    assert transaction(client, base, 'adjust', 100, price=10).status_code == 200
    h = session.get(Holding, holdings(client)[0]['id'])
    h.current_price = 12
    h.price_updated_at = datetime(2026, 9, 1, 12)
    session.add(h)
    session.commit()
    record_daily_pnl(session, user.id, now=datetime(2026, 9, 1, 12))
    assert transaction(client, base, 'adjust', 200, price=10, date='2026-09-02').status_code == 200
    session.expire_all()
    h.price_updated_at = datetime(2026, 9, 2, 12)
    session.add(h)
    session.commit()
    result = record_daily_pnl(session, user.id, now=datetime(2026, 9, 2, 12))
    assert result.status == 'adjusted', result.model_dump()
    assert result.pnl_cny is None


def test_edit_existing_transaction_into_manual_sale_preserves_opening_order(client):
    base, _ = setup_position(client)
    record = transaction(client, base, 'other', 20).json()
    updated = client.put(f"/api/transactions/{record['id']}", json={'action': 'sell'})
    assert updated.status_code == 200, updated.text
    h, = holdings(client)
    assert h['quantity'] == 80
    assert h['realized_pnl'] == 40


def test_csv_failure_does_not_leave_partial_import(client):
    base, _ = setup_position(client)
    assert transaction(client, base, 'adjust', 100, date='2026-09-10').status_code == 200
    content = ('date,action,name,symbol,platform,currency,quantity,price,amount\n'
               '2026-09-01,deposit,,,Calibration,USD,,,50\n'
               '2026-09-05,sell,Apple,AAPL,Calibration,USD,20,12,')
    files = {'file': ('invalid-history.csv', content.encode(), 'text/csv')}
    response = client.post('/api/transactions/import/commit', files=files)
    assert response.status_code == 400
    txns = client.get('/api/transactions').json()
    assert len(txns) == 1
    assert txns[0]['action'] == 'adjust'
    assert len(holdings(client)) == 1


def test_existing_database_adds_incomplete_cost_flag_idempotently(monkeypatch):
    import database
    from sqlalchemy import text
    from sqlmodel import create_engine
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE holding (id INTEGER PRIMARY KEY)'))
        conn.execute(text('INSERT INTO holding (id) VALUES (1)'))
    monkeypatch.setattr(database, 'engine', engine)
    monkeypatch.setattr(database, 'IS_SQLITE', True)
    database._migrate_add_user_id()
    database._migrate_add_user_id()
    with engine.connect() as conn:
        assert conn.execute(text('SELECT realized_pnl_incomplete FROM holding WHERE id=1')).scalar() == 0


def test_broker_import_calibration_and_sell(client):
    base, _ = setup_position(client)
    content = ('date,action,name,symbol,currency,quantity,price\n'
               '2026-09-01,adjust,Apple,AAPL,USD,120,10\n'
               '2026-09-01,sell,Apple,AAPL,USD,110,12')
    preview = client.post('/api/imports/preview',
                          data={'broker_type': 'generic', 'platform_id': base['platform_id']},
                          files={'file': ('calibration.csv', content.encode(), 'text/csv')})
    assert preview.json()['summary']['error'] == 0, preview.json()
    committed = client.post(f"/api/imports/{preview.json()['import_session_id']}/commit")
    assert committed.json()['created_count'] == 2, committed.json()
    h, = holdings(client)
    assert h['quantity'] == 10
    assert h['realized_pnl'] == 220
