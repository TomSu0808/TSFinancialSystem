"""自动化任务接口和服务测试。"""
import pytest
from sqlmodel import Session, select


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _platform(client, name="Futu"):
    r = client.post("/api/platforms", json={"name": name})
    assert r.status_code == 200
    return r.json()["id"]


def _holding(client, pid, symbol="AAPL", name="Apple"):
    r = client.post("/api/holdings", json={
        "platform_id": pid, "currency": "USD", "symbol": symbol,
        "name": name, "quantity": 10, "cost_price": 100,
        "market": "US", "asset_type": "stock",
    })
    assert r.status_code == 200
    return r.json()["id"]


# ── /api/automation/status ────────────────────────────────────────────────────

def test_automation_status_structure(client):
    r = client.get("/api/automation/status")
    assert r.status_code == 200
    body = r.json()
    assert "enabled" in body
    assert "schedule_time" in body
    assert "interval_hours" in body
    assert "timezone" in body
    assert "last_run" in body


def test_automation_status_no_runs_yet(client):
    r = client.get("/api/automation/status")
    assert r.status_code == 200
    assert r.json()["last_run"] is None


# ── /api/automation/run-now ───────────────────────────────────────────────────

def test_run_now_creates_automation_run(client, session):
    from models import AutomationRun
    pid = _platform(client)
    _holding(client, pid)

    r = client.post("/api/automation/run-now")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("success", "partial_failed", "failed")
    assert body["triggered_by"] == "manual"

    # DB 有记录
    runs = session.exec(select(AutomationRun)).all()
    assert len(runs) >= 1


def test_run_now_records_user_count(client, session):
    r = client.post("/api/automation/run-now")
    assert r.status_code == 200
    body = r.json()
    assert body["users_total"] == 1   # 单用户模式
    assert body["users_succeeded"] >= 0


def test_run_now_saves_snapshot(client, session):
    from models import Snapshot
    pid = _platform(client)
    _holding(client, pid)
    client.post("/api/automation/run-now")
    snaps = session.exec(select(Snapshot)).all()
    assert len(snaps) >= 1


def test_run_now_partial_fail_still_records(client, session, monkeypatch):
    """即使行情刷新抛异常，AutomationRun 也要记录结果。"""
    from models import AutomationRun
    import automation_service

    def _bad_refresh(session, user_id):
        raise RuntimeError("mock failure")

    monkeypatch.setattr(automation_service, "_refresh_user_holdings", _bad_refresh)

    r = client.post("/api/automation/run-now")
    # 接口不应 500（任务失败要被捕获）
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "failed"


# ── /api/automation/runs ──────────────────────────────────────────────────────

def test_list_runs_empty(client):
    r = client.get("/api/automation/runs")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_list_runs_after_run_now(client):
    client.post("/api/automation/run-now")
    r = client.get("/api/automation/runs")
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_list_runs_limit(client):
    for _ in range(3):
        client.post("/api/automation/run-now")
    r = client.get("/api/automation/runs")
    assert r.status_code == 200
    assert len(r.json()) <= 20


# ── run_all_users_job ─────────────────────────────────────────────────────────

def test_run_all_users_job_direct(session, user):
    """直接调用服务函数，验证返回 AutomationRun。"""
    from automation_service import run_all_users_job
    from models import AutomationRun
    run = run_all_users_job(session, triggered_by="scheduler")
    assert isinstance(run, AutomationRun)
    assert run.status in ("success", "partial_failed", "failed")
    assert run.users_total == 1
    assert run.finished_at is not None


def test_upsert_snapshot_via_service(session, user):
    """_upsert_snapshot 可独立调用。"""
    from automation_service import _upsert_snapshot
    from models import Snapshot
    _upsert_snapshot(session, user.id)
    snaps = session.exec(select(Snapshot).where(Snapshot.user_id == user.id)).all()
    assert len(snaps) == 1
    # 再调一次：更新，不新增
    _upsert_snapshot(session, user.id)
    snaps2 = session.exec(select(Snapshot).where(Snapshot.user_id == user.id)).all()
    assert len(snaps2) == 1
