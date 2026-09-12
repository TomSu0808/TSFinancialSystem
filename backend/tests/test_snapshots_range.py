"""快照 range 参数与日历边界测试。"""
from datetime import date

from routers.snapshots import _range_start


def test_filters_malformed_and_future_dates(client, session, user):
    from models import Snapshot
    from datetime import datetime, timedelta
    today = datetime.utcnow().date()
    for day in (None, "", "2026-02-30", "2026-1-1", (today + timedelta(days=1)).isoformat(), today.isoformat()):
        session.add(Snapshot(user_id=user.id, day=day, total_cny=100))
    session.commit()
    assert [r['day'] for r in client.get('/api/snapshots?range=max').json()] == [today.isoformat()]


def test_range_start_month_end_and_leap():
    assert _range_start("1m", date(2026, 3, 31)) == "2026-02-28"
    assert _range_start("1m", date(2024, 3, 31)) == "2024-02-29"   # 闰年 2 月 29
    assert _range_start("1y", date(2024, 2, 29)) == "2023-02-28"   # 闰日回溯 1 年
    assert _range_start("3m", date(2026, 5, 31)) == "2026-02-28"
    assert _range_start("6m", date(2026, 8, 31)) == "2026-02-28"


def test_range_start_week_and_max():
    assert _range_start("1w", date(2026, 1, 10)) == "2026-01-04"  # 今天及之前 6 天 = 7 天
    assert _range_start("max", date(2026, 1, 1)) is None


from datetime import datetime, timedelta

from models import Snapshot


def _seed(session, user_id, day, cny=100.0, usd=10.0):
    session.add(Snapshot(user_id=user_id, day=day, total_cny=cny, total_usd=usd))
    session.commit()


def test_six_ranges_and_max_no_upper_bound(client, session, user):
    old = (datetime.utcnow() - timedelta(days=365 * 12)).strftime("%Y-%m-%d")  # 12 年前
    _seed(session, user.id, old, cny=1.0, usd=0.1)
    _seed(session, user.id, (datetime.utcnow() - timedelta(days=2)).strftime("%Y-%m-%d"))
    _seed(session, user.id, datetime.utcnow().strftime("%Y-%m-%d"))

    r = client.get("/api/snapshots", params={"range": "max"})
    assert r.status_code == 200
    days = [x["day"] for x in r.json()]
    assert old in days  # max 包含超过 10 年的历史

    for key in ("1y", "6m", "3m", "1m", "1w"):
        r = client.get("/api/snapshots", params={"range": key})
        assert r.status_code == 200
        assert [x["day"] for x in r.json()] == sorted(x["day"] for x in r.json())  # 升序


def test_invalid_range_returns_400(client):
    r = client.get("/api/snapshots", params={"range": "bad"})
    assert r.status_code == 400


def test_range_wins_over_days(client, session, user):
    _seed(session, user.id, (datetime.utcnow() - timedelta(days=100)).strftime("%Y-%m-%d"))
    _seed(session, user.id, datetime.utcnow().strftime("%Y-%m-%d"))
    r = client.get("/api/snapshots", params={"range": "1w", "days": 3650})
    days = [x["day"] for x in r.json()]
    assert len(days) == 1  # 只返回 1 周内（忽略 days）


def test_days_backward_compat(client, session, user):
    _seed(session, user.id, (datetime.utcnow() - timedelta(days=200)).strftime("%Y-%m-%d"))
    _seed(session, user.id, datetime.utcnow().strftime("%Y-%m-%d"))
    r = client.get("/api/snapshots", params={"days": 90})
    assert r.status_code == 200
    assert len(r.json()) == 1  # 旧 days 参数仍生效


def test_empty_range_returns_empty(client):
    r = client.get("/api/snapshots", params={"range": "1w"})
    assert r.status_code == 200
    assert r.json() == []


def test_user_isolation(client, session, user):
    from models import User
    other = User(username="other", password_hash="x")
    session.add(other)
    session.commit()
    _seed(session, other.id, datetime.utcnow().strftime("%Y-%m-%d"), cny=999.0, usd=99.0)
    r = client.get("/api/snapshots", params={"range": "max"})
    assert all(x["total_cny"] != 999.0 for x in r.json())
