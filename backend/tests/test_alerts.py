"""提醒规则和事件接口测试。"""
from datetime import datetime, timedelta

import pytest
from sqlmodel import Session, select


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _platform(client, name="Futu"):
    r = client.post("/api/platforms", json={"name": name})
    assert r.status_code == 200
    return r.json()["id"]


def _holding(client, pid, symbol="AAPL", name="Apple", price=150.0):
    r = client.post("/api/holdings", json={
        "platform_id": pid, "currency": "USD", "symbol": symbol,
        "name": name, "quantity": 10, "cost_price": 100,
        "market": "US", "asset_type": "stock",
    })
    assert r.status_code == 200
    return r.json()["id"]


def _rule(client, **kwargs):
    payload = {"name": "测试规则", "alert_type": "price_above", "threshold_value": 200, **kwargs}
    r = client.post("/api/alerts/rules", json=payload)
    assert r.status_code == 200
    return r.json()


# ── 规则 CRUD ─────────────────────────────────────────────────────────────────

def test_create_rule(client):
    body = _rule(client)
    assert body["id"] is not None
    assert body["alert_type"] == "price_above"
    assert body["enabled"] is True


def test_list_rules(client):
    _rule(client)
    _rule(client, name="规则2", alert_type="price_below")
    r = client.get("/api/alerts/rules")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_update_rule(client):
    rule = _rule(client)
    r = client.put(f"/api/alerts/rules/{rule['id']}", json={"enabled": False, "threshold_value": 100})
    assert r.status_code == 200
    assert r.json()["enabled"] is False
    assert r.json()["threshold_value"] == 100


def test_delete_rule(client):
    rule = _rule(client)
    r = client.delete(f"/api/alerts/rules/{rule['id']}")
    assert r.status_code == 200
    assert client.get("/api/alerts/rules").json() == []


def test_create_rule_with_valid_holding(client):
    pid = _platform(client)
    hid = _holding(client, pid)
    rule = _rule(client, holding_id=hid)
    assert rule["holding_id"] == hid


def test_create_rule_with_invalid_holding_404(client, session):
    from models import User
    from sqlmodel import select as sel
    u2_id = 9999  # 不存在的 holding
    r = client.post("/api/alerts/rules", json={
        "name": "bad", "alert_type": "price_above",
        "threshold_value": 100, "holding_id": u2_id,
    })
    assert r.status_code == 404


def test_rule_user_isolation(client, session):
    """其他用户的规则不可见。"""
    from models import AlertRule, User
    u2 = User(username="other_alert", password_hash="x")
    session.add(u2)
    session.commit()
    other_rule = AlertRule(user_id=u2.id, name="他人规则", alert_type="price_above")
    session.add(other_rule)
    session.commit()

    r = client.get("/api/alerts/rules")
    ids = [x["id"] for x in r.json()]
    assert other_rule.id not in ids


# ── 事件 CRUD ─────────────────────────────────────────────────────────────────

def test_events_empty_initially(client):
    r = client.get("/api/alerts/events")
    assert r.status_code == 200
    assert r.json() == []


def test_mark_event_read(client, session, user):
    from models import AlertEvent
    ev = AlertEvent(user_id=user.id, alert_type="price_above", title="T", message="M", status="unread")
    session.add(ev)
    session.commit()

    r = client.post(f"/api/alerts/events/{ev.id}/read")
    assert r.status_code == 200
    session.refresh(ev)
    assert ev.status == "read"


def test_dismiss_event(client, session, user):
    from models import AlertEvent
    ev = AlertEvent(user_id=user.id, alert_type="price_below", title="T", message="M", status="unread")
    session.add(ev)
    session.commit()

    r = client.post(f"/api/alerts/events/{ev.id}/dismiss")
    assert r.status_code == 200
    session.refresh(ev)
    assert ev.status == "dismissed"


def test_mark_all_read(client, session, user):
    from models import AlertEvent
    for i in range(3):
        session.add(AlertEvent(user_id=user.id, alert_type="price_above",
                               title=f"T{i}", message="M", status="unread"))
    session.commit()

    r = client.post("/api/alerts/events/read-all")
    assert r.status_code == 200
    assert r.json()["updated"] == 3

    r2 = client.get("/api/alerts/events", params={"status": "unread"})
    assert r2.json() == []


def test_unread_count(client, session, user):
    from models import AlertEvent
    for _ in range(2):
        session.add(AlertEvent(user_id=user.id, alert_type="price_above",
                               title="T", message="M", status="unread"))
    session.commit()

    r = client.get("/api/alerts/events/unread-count")
    assert r.status_code == 200
    assert r.json()["count"] == 2


def test_events_user_isolation(client, session, user):
    """其他用户的事件不可见。"""
    from models import AlertEvent, User
    u2 = User(username="other_ev", password_hash="x")
    session.add(u2)
    session.commit()
    other_ev = AlertEvent(user_id=u2.id, alert_type="price_above",
                          title="other", message="M", status="unread")
    session.add(other_ev)
    session.commit()

    r = client.get("/api/alerts/events")
    ids = [e["id"] for e in r.json()]
    assert other_ev.id not in ids


# ── 提醒评估逻辑 ──────────────────────────────────────────────────────────────

def _set_holding_price(session, hid, current, prev):
    from models import Holding
    h = session.get(Holding, hid)
    h.current_price = current
    h.prev_close = prev
    h.price_updated_at = datetime.utcnow()
    session.add(h)
    session.commit()


def test_evaluate_price_above_triggers(client, session, user):
    pid = _platform(client)
    hid = _holding(client, pid, price=150)
    _set_holding_price(session, hid, current=200, prev=190)

    rule = _rule(client, alert_type="price_above", threshold_value=195, holding_id=hid)

    r = client.post("/api/alerts/evaluate")
    assert r.status_code == 200
    assert r.json()["triggered"] >= 1

    events = client.get("/api/alerts/events").json()
    assert any(e["alert_type"] == "price_above" for e in events)


def test_evaluate_price_below_triggers(client, session, user):
    pid = _platform(client)
    hid = _holding(client, pid)
    _set_holding_price(session, hid, current=80, prev=90)
    _rule(client, alert_type="price_below", threshold_value=100, holding_id=hid)

    r = client.post("/api/alerts/evaluate")
    assert r.status_code == 200
    assert r.json()["triggered"] >= 1


def test_evaluate_allocation_above_triggers(client, session, user):
    from models import FxRate
    # 确保有汇率
    fx = session.get(FxRate, "USDCNY")
    if not fx:
        session.add(FxRate(pair="USDCNY", rate=7.2))
        session.commit()

    pid = _platform(client)
    hid = _holding(client, pid, symbol="ONLY")
    _set_holding_price(session, hid, current=200, prev=190)

    # 只有这一个持仓，占比 100%
    _rule(client, alert_type="allocation_above", threshold_value=50, holding_id=hid)

    r = client.post("/api/alerts/evaluate")
    assert r.status_code == 200
    assert r.json()["triggered"] >= 1


def test_evaluate_price_stale_triggers(client, session, user):
    pid = _platform(client)
    hid = _holding(client, pid, symbol="STALE")
    from models import Holding
    h = session.get(Holding, hid)
    h.price_updated_at = datetime.utcnow() - timedelta(hours=50)
    session.add(h)
    session.commit()

    _rule(client, alert_type="price_stale", stale_hours=24)

    r = client.post("/api/alerts/evaluate")
    assert r.status_code == 200
    assert r.json()["triggered"] >= 1


def test_evaluate_no_duplicate_same_day(client, session, user):
    """同一规则当天不重复触发。"""
    pid = _platform(client)
    hid = _holding(client, pid)
    _set_holding_price(session, hid, current=200, prev=190)
    _rule(client, alert_type="price_above", threshold_value=195, holding_id=hid)

    # 第一次触发
    r1 = client.post("/api/alerts/evaluate")
    count1 = r1.json()["triggered"]

    # 第二次不应再触发同一条
    r2 = client.post("/api/alerts/evaluate")
    count2 = r2.json()["triggered"]

    assert count2 == 0  # 去重生效


def test_evaluate_price_above_not_triggered_when_below(client, session, user):
    pid = _platform(client)
    hid = _holding(client, pid)
    _set_holding_price(session, hid, current=100, prev=90)
    _rule(client, alert_type="price_above", threshold_value=200, holding_id=hid)

    r = client.post("/api/alerts/evaluate")
    assert r.json()["triggered"] == 0
