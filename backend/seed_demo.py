"""Demo 数据初始化脚本（可重复运行，幂等）。

创建一个 demo 用户及典型数据：
- 多平台（富途、盈透、银行）
- CNY / USD / HKD 持仓
- 买入 / 卖出 / 分红交易
- 手填现金 / 债券
- 投资笔记 / 行动项

运行方式：
    cd backend
    python seed_demo.py

重复运行不会无限插入重复数据（按 username 判断是否已存在）。
"""
import sys
from datetime import datetime, timedelta

from sqlmodel import Session, select

from auth import hash_password
from database import init_db, engine
from models import (
    AlertRule, Currency, Holding, HoldingSource, HoldingStatus,
    Note, Platform, Transaction, TxnAction, User,
)

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo123456"
DEMO_EMAIL = "demo@example.com"


def _ensure_demo_user(session: Session) -> User:
    """确保 demo 用户存在，返回用户对象。"""
    existing = session.exec(
        select(User).where(User.username == DEMO_USERNAME)
    ).first()
    if existing:
        print(f"[seed] Demo 用户已存在 (id={existing.id})，跳过创建。")
        return existing

    user = User(
        username=DEMO_USERNAME,
        email=DEMO_EMAIL,
        password_hash=hash_password(DEMO_PASSWORD),
        email_verified=True,
        email_verified_at=datetime.utcnow(),
        status="active",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    print(f"[seed] 创建 Demo 用户 (id={user.id}, password={DEMO_PASSWORD})")
    return user


def _ensure_platforms(session: Session, user: User) -> dict:
    """确保平台存在（按名称去重），返回 {name: id} 字典。"""
    existing = session.exec(
        select(Platform).where(Platform.user_id == user.id)
    ).all()
    plat_map = {p.name: p.id for p in existing}

    wanted = [
        ("富途证券", "港股/美股券商"),
        ("盈透证券 (IBKR)", "美股/全球券商"),
        ("招商银行", "人民币现金/理财"),
        ("币安", "加密货币交易"),
    ]
    for name, note in wanted:
        if name not in plat_map:
            p = Platform(user_id=user.id, name=name, note=note)
            session.add(p)
            session.commit()
            session.refresh(p)
            plat_map[name] = p.id
            print(f"[seed] 创建平台：{name}")
    return plat_map


def _ensure_holdings(session: Session, user: User, plat_map: dict) -> None:
    """确保 demo 持仓存在（按 user+symbol+currency+source 去重）。"""
    existing = session.exec(
        select(Holding).where(Holding.user_id == user.id)
    ).all()
    existing_keys = {(h.symbol, h.currency, h.source, h.platform_id) for h in existing}

    today = datetime.utcnow()
    price_ts = today - timedelta(hours=2)

    holdings_data = [
        # 富途 - 港股（HKD）
        {"platform": "富途证券", "symbol": "0700", "name": "腾讯控股", "currency": Currency.HKD,
         "market": "HK", "asset_type": "stock", "source": HoldingSource.derived,
         "quantity": 200, "cost_price": 350, "current_price": 390, "prev_close": 385},
        {"platform": "富途证券", "symbol": "9988", "name": "阿里巴巴-SW", "currency": Currency.HKD,
         "market": "HK", "asset_type": "stock", "source": HoldingSource.derived,
         "quantity": 300, "cost_price": 85, "current_price": 92, "prev_close": 90},
        # 富途 - 美股（USD）
        {"platform": "富途证券", "symbol": "AAPL", "name": "Apple Inc.", "currency": Currency.USD,
         "market": "US", "asset_type": "stock", "source": HoldingSource.derived,
         "quantity": 50, "cost_price": 175, "current_price": 192, "prev_close": 190},
        # 盈透 - 美股（USD）
        {"platform": "盈透证券 (IBKR)", "symbol": "MSFT", "name": "Microsoft Corp.", "currency": Currency.USD,
         "market": "US", "asset_type": "stock", "source": HoldingSource.derived,
         "quantity": 30, "cost_price": 380, "current_price": 425, "prev_close": 420},
        {"platform": "盈透证券 (IBKR)", "symbol": "VOO", "name": "Vanguard S&P 500 ETF", "currency": Currency.USD,
         "market": "US", "asset_type": "etf", "source": HoldingSource.derived,
         "quantity": 80, "cost_price": 480, "current_price": 520, "prev_close": 515},
        # 招商银行 - 手动资产（CNY）
        {"platform": "招商银行", "symbol": "", "name": "现金存款", "currency": Currency.CNY,
         "market": "NONE", "asset_type": "cash", "source": HoldingSource.manual,
         "manual_value": 50000},
        {"platform": "招商银行", "symbol": "", "name": "招商产业债券A", "currency": Currency.CNY,
         "market": "FUND", "asset_type": "bond", "source": HoldingSource.manual,
         "manual_value": 100000},
    ]

    for hd in holdings_data:
        pid = plat_map.get(hd["platform"])
        if pid is None:
            continue
        key = (hd["symbol"], hd["currency"], hd["source"], pid)
        if key in existing_keys:
            continue
        h = Holding(
            user_id=user.id,
            platform_id=pid,
            name=hd["name"],
            symbol=hd["symbol"],
            currency=hd["currency"],
            market=hd["market"],
            asset_type=hd["asset_type"],
            source=hd["source"],
            quantity=hd.get("quantity"),
            manual_value=hd.get("manual_value"),
            cost_price=hd.get("cost_price"),
            current_price=hd.get("current_price"),
            prev_close=hd.get("prev_close"),
            price_updated_at=price_ts,
            realized_pnl=hd.get("realized_pnl", 0),
            realized_income=hd.get("realized_income", 0),
            status=HoldingStatus.open,
        )
        session.add(h)
        existing_keys.add(key)
        print(f"[seed] 创建持仓：{hd['name']} ({hd.get('symbol', '-')}) [{hd['currency'].value}]")

    session.commit()


def _ensure_transactions(session: Session, user: User, plat_map: dict) -> None:
    """确保 demo 交易存在（按 user+symbol+date+action+quantity 去重）。"""
    existing = session.exec(
        select(Transaction).where(Transaction.user_id == user.id)
    ).all()
    existing_keys = {
        (t.symbol, t.date, t.action, t.quantity, t.platform_id) for t in existing
    }

    txns_data = [
        # 腾讯买入
        {"platform": "富途证券", "date": "2026-01-15", "action": TxnAction.buy,
         "name": "腾讯控股", "symbol": "0700", "currency": Currency.HKD,
         "quantity": 200, "price": 350, "fee": 50, "note": "建仓"},
        # 阿里买入
        {"platform": "富途证券", "date": "2026-02-10", "action": TxnAction.buy,
         "name": "阿里巴巴-SW", "symbol": "9988", "currency": Currency.HKD,
         "quantity": 300, "price": 85, "fee": 30, "note": "建仓"},
        # Apple 买入
        {"platform": "富途证券", "date": "2026-03-05", "action": TxnAction.buy,
         "name": "Apple Inc.", "symbol": "AAPL", "currency": Currency.USD,
         "quantity": 50, "price": 175, "fee": 1.5, "note": "买入苹果"},
        # MSFT 买入
        {"platform": "盈透证券 (IBKR)", "date": "2026-01-20", "action": TxnAction.buy,
         "name": "Microsoft Corp.", "symbol": "MSFT", "currency": Currency.USD,
         "quantity": 30, "price": 380, "fee": 1.0, "note": "建仓微软"},
        # VOO 买入
        {"platform": "盈透证券 (IBKR)", "date": "2026-04-01", "action": TxnAction.buy,
         "name": "Vanguard S&P 500 ETF", "symbol": "VOO", "currency": Currency.USD,
         "quantity": 100, "price": 480, "fee": 0.5, "note": "定投标普500"},
        # VOO 部分卖出
        {"platform": "盈透证券 (IBKR)", "date": "2026-06-15", "action": TxnAction.sell,
         "name": "Vanguard S&P 500 ETF", "symbol": "VOO", "currency": Currency.USD,
         "quantity": 20, "price": 515, "fee": 0.5, "note": "止盈 20 股"},
        # 腾讯分红
        {"platform": "富途证券", "date": "2026-05-20", "action": TxnAction.dividend,
         "name": "腾讯控股", "symbol": "0700", "currency": Currency.HKD,
         "amount": 680, "note": "年度分红"},
    ]

    for td in txns_data:
        pid = plat_map.get(td["platform"])
        if pid is None:
            continue
        key = (td["symbol"], td["date"], str(td["action"]), td.get("quantity"), pid)
        if key in existing_keys:
            continue
        t = Transaction(
            user_id=user.id,
            platform_id=pid,
            date=td["date"],
            action=td["action"],
            name=td["name"],
            symbol=td["symbol"],
            currency=td["currency"],
            quantity=td.get("quantity"),
            price=td.get("price"),
            fee=td.get("fee"),
            amount=td.get("amount"),
            note=td.get("note"),
        )
        session.add(t)
        existing_keys.add(key)
        label = f"{td['action'].value} {td['symbol']} x{td.get('quantity', '-')}"
        print(f"[seed] 创建交易：{label}")

    session.commit()


def _ensure_notes(session: Session, user: User) -> None:
    """确保 demo 笔记存在（按 title+user_id 去重）。"""
    existing = session.exec(
        select(Note).where(Note.user_id == user.id)
    ).all()
    existing_titles = {n.title for n in existing}

    notes_data = [
        {
            "title": "腾讯2026Q1财报复盘",
            "content": "腾讯Q1游戏收入增长超预期，广告业务稳健。继续保持持仓，目标价420 HKD。\n\n风险点：监管政策不确定。",
            "note_type": "review",
            "symbol": "0700",
            "tags": "腾讯,财报,复盘",
        },
        {
            "title": "标普500定投计划",
            "content": "每月1日定投VOO $500。长期持有，不做波段。\n\n行动项：每季度复盘一次定投执行情况。",
            "note_type": "action",
            "symbol": "VOO",
            "tags": "定投,标普500,长期",
        },
        {
            "title": "Apple Vision Pro市场观察",
            "content": "Vision Pro销量不及预期，但长期看好空间计算赛道。\n\n待验证：2026Q3开发者生态数据。",
            "note_type": "observation",
            "symbol": "AAPL",
            "tags": "苹果,VisionPro,观察",
        },
    ]

    for nd in notes_data:
        if nd["title"] in existing_titles:
            continue
        n = Note(
            user_id=user.id,
            title=nd["title"],
            content=nd["content"],
            note_type=nd["note_type"],
            symbol=nd["symbol"],
            tags=nd["tags"],
            status="active",
        )
        session.add(n)
        print(f"[seed] 创建笔记：{nd['title']}")

    session.commit()


def _ensure_alerts(session: Session, user: User) -> None:
    """确保 Demo 用户有一些提醒规则。"""
    existing = session.exec(
        select(AlertRule).where(AlertRule.user_id == user.id)
    ).all()
    if existing:
        print("[seed] 提醒规则已存在，跳过。")
        return

    rules = [
        AlertRule(
            user_id=user.id, name="腾讯价格预警",
            alert_type="price_below", symbol="0700", currency="HKD",
            threshold_value=320, enabled=True,
        ),
        AlertRule(
            user_id=user.id, name="行情过期提醒",
            alert_type="price_stale", stale_hours=24, enabled=True,
        ),
    ]
    for r in rules:
        session.add(r)
    session.commit()
    print(f"[seed] 创建 {len(rules)} 条提醒规则")


def main():
    init_db()

    with Session(engine) as session:
        user = _ensure_demo_user(session)
        plat_map = _ensure_platforms(session, user)
        _ensure_holdings(session, user, plat_map)
        _ensure_transactions(session, user, plat_map)
        _ensure_notes(session, user)
        _ensure_alerts(session, user)

    print("\n[seed] ✅ Demo 数据初始化完成。")
    print(f"[seed] 登录账号：{DEMO_USERNAME} / {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
