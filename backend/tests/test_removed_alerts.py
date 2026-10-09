import pytest


@pytest.mark.parametrize('method,path', [
    ('get', '/api/alerts/rules'),
    ('get', '/api/alerts/events'),
    ('get', '/api/alerts/events/unread-count'),
    ('post', '/api/alerts/evaluate'),
])
def test_alert_endpoints_are_removed(client, method, path):
    assert getattr(client, method)(path).status_code in (404, 405)


def test_alerts_are_not_part_of_api_or_new_database(client, engine):
    from sqlalchemy import inspect
    assert not any(path.startswith('/api/alerts') for path in client.get('/openapi.json').json()['paths'])
    assert not {'alertrule', 'alertevent'} & set(inspect(engine).get_table_names())


def test_legacy_reminders_no_longer_block_holding_deletion(engine, session, user, monkeypatch):
    from sqlalchemy import text
    from models import Holding, Platform
    import database
    platform = Platform(user_id=user.id, name='Legacy account')
    session.add(platform)
    session.commit()
    holding = Holding(user_id=user.id, platform_id=platform.id, name='Legacy holding')
    session.add(holding)
    session.commit()
    with engine.begin() as conn:
        conn.execute(text('PRAGMA foreign_keys=ON'))
        conn.execute(text('CREATE TABLE alertrule (id INTEGER PRIMARY KEY, holding_id INTEGER REFERENCES holding(id), name TEXT)'))
        conn.execute(text('CREATE TABLE alertevent (id INTEGER PRIMARY KEY, holding_id INTEGER REFERENCES holding(id), message TEXT)'))
        conn.execute(text("INSERT INTO alertrule VALUES (1, :hid, 'old rule')"), {'hid': holding.id})
        conn.execute(text("INSERT INTO alertevent VALUES (1, :hid, 'old event')"), {'hid': holding.id})
    monkeypatch.setattr(database, 'engine', engine)
    database.init_db()
    database.init_db()
    session.delete(holding)
    session.commit()
    with engine.connect() as conn:
        assert conn.execute(text('SELECT holding_id, message FROM alertevent')).one() == (None, 'old event')
