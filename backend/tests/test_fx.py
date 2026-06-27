from datetime import datetime, timedelta

from sqlmodel import Session

from models import FxRate


def test_get_rate_refreshes_missing_cache(client):
    from routers import fx

    original_fetch = fx.fetch_usdcny
    fx.fetch_usdcny = lambda: 7.31
    try:
        resp = client.get("/api/fx/rate")
    finally:
        fx.fetch_usdcny = original_fetch

    assert resp.status_code == 200
    data = resp.json()
    assert data["rate"] == 7.31
    assert data["updated_at"] is not None


def test_get_rate_keeps_fresh_cache(client, engine):
    from routers import fx

    with Session(engine) as session:
        session.add(FxRate(pair="USDCNY", rate=7.22, updated_at=datetime.utcnow()))
        session.commit()

    original_fetch = fx.fetch_usdcny
    fx.fetch_usdcny = lambda: 7.99
    try:
        resp = client.get("/api/fx/rate")
    finally:
        fx.fetch_usdcny = original_fetch

    assert resp.status_code == 200
    assert resp.json()["rate"] == 7.22


def test_get_rate_refreshes_stale_cache(client, engine):
    from routers import fx

    with Session(engine) as session:
        session.add(FxRate(
            pair="USDCNY",
            rate=7.2,
            updated_at=datetime.utcnow() - timedelta(days=1),
        ))
        session.commit()

    original_fetch = fx.fetch_usdcny
    fx.fetch_usdcny = lambda: 7.35
    try:
        resp = client.get("/api/fx/rate")
    finally:
        fx.fetch_usdcny = original_fetch

    assert resp.status_code == 200
    assert resp.json()["rate"] == 7.35
