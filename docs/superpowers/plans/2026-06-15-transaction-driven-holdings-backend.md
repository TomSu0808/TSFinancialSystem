# 交易驱动持仓 · 后端引擎 Implementation Plan (Plan 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 derived（交易驱动）持仓的数量、移动加权成本、已实现盈亏由交易流水自动派生，manual（手填）持仓行为完全不变。

**Architecture:** 纯逻辑 `replay_transactions`（按日期重放流水，无副作用）与带 DB 副作用的 `recompute_holding` 分离，置于新模块 `backend/position.py`；交易路由在增删改后触发对应持仓全量重算。SQLite 幂等迁移补列，存量数据默认 manual 零影响。

**Tech Stack:** FastAPI · SQLModel · SQLite · pytest

**配套设计文档:** [docs/superpowers/specs/2026-06-15-transaction-driven-holdings-design.md](../specs/2026-06-15-transaction-driven-holdings-design.md)

---

## File Structure

- **Create** `backend/position.py` — 派生计算核心：`PositionState`、`replay_transactions`（纯）、`resolve_derived_holding`、`recompute_holding`（副作用）
- **Create** `backend/tests/conftest.py` — pytest fixtures：内存 SQLite session、TestClient（覆盖鉴权）
- **Create** `backend/tests/test_position.py` — 派生算法单测（重点）
- **Create** `backend/tests/test_transactions_drive_holdings.py` — 路由集成测试
- **Modify** `backend/models.py` — 新增枚举 `HoldingSource`/`HoldingStatus`；`Holding`/`Transaction` 加字段；`HoldingCreate`/`TransactionCreate`/`TransactionUpdate` 加字段
- **Modify** `backend/database.py` — `init_db` 幂等迁移补列
- **Modify** `backend/routers/transactions.py` — 增删改后触发重算 + 自动创建 derived 持仓
- **Modify** `backend/routers/holdings.py` — `include_closed`、derived 拒绝手改数量/成本、create 接受 source
- **Modify** `backend/routers/summary.py` — 收益拆分 unrealized / realized_pnl / realized_income / total_return
- **Modify** `backend/routers/backup.py` — 导入旧备份缺字段给默认值
- **Modify** `backend/requirements.txt` — 加 `pytest`、`httpx`（TestClient 依赖）

---

## Task 0: 测试基础设施

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/pytest.ini`

- [ ] **Step 1: 加测试依赖到 requirements.txt**

在 `backend/requirements.txt` 末尾追加：

```
# 测试
pytest>=8.0
httpx>=0.27
```

- [ ] **Step 2: 安装到 venv**

Run: `backend/.venv/bin/python -m pip install pytest httpx`
Expected: 成功安装（`Successfully installed ...`）

- [ ] **Step 3: 创建 pytest 配置**

Create `backend/pytest.ini`：

```ini
[pytest]
testpaths = tests
python_files = test_*.py
```

- [ ] **Step 4: 创建 tests 包**

Create `backend/tests/__init__.py`（空文件）。

- [ ] **Step 5: 创建 conftest.py（内存库 session + 鉴权覆盖的 client）**

Create `backend/tests/conftest.py`：

```python
"""测试夹具：每个测试用独立内存 SQLite，TestClient 覆盖鉴权为固定测试用户。"""
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

import models  # noqa: F401  确保模型注册到 metadata


@pytest.fixture(name="engine")
def engine_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(name="session")
def session_fixture(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture(name="user")
def user_fixture(session):
    from models import User
    u = User(username="tester", password_hash="x")
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


@pytest.fixture(name="client")
def client_fixture(engine, user):
    from main import app
    from database import get_session
    from auth import get_current_user

    def get_session_override():
        with Session(engine) as session:
            yield session

    def get_current_user_override():
        with Session(engine) as session:
            from models import User
            return session.get(User, user.id)

    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_current_user] = get_current_user_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
```

- [ ] **Step 6: 冒烟验证 pytest 能跑**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: `no tests ran`（无测试但 conftest 无导入错误）

- [ ] **Step 7: Commit**

```bash
cd "/Volumes/T7 Shield/Study/CS/FinancialSystem"
find . -name '._*' -delete
git add backend/requirements.txt backend/pytest.ini backend/tests/
git commit -m "test: add pytest infrastructure (in-memory db + auth-overridden client)"
```

---

## Task 1: 数据模型新增字段

**Files:**
- Modify: `backend/models.py`

- [ ] **Step 1: 加两个枚举**

在 `backend/models.py` 的 `Market` 枚举之后加：

```python
class HoldingSource(str, Enum):
    manual = "manual"      # 手填型：数量/成本用户直接维护
    derived = "derived"    # 交易驱动型：数量/成本由交易流水派生


class HoldingStatus(str, Enum):
    open = "open"
    closed = "closed"      # 清仓（数量归零），主列表默认隐藏
```

- [ ] **Step 2: 给 `Holding` 表加字段**

在 `Holding` 类的 `price_updated_at` 字段之后加：

```python
    source: HoldingSource = HoldingSource.manual
    status: HoldingStatus = HoldingStatus.open
    realized_pnl: float = 0.0       # 累计已实现盈亏（derived）
    realized_income: float = 0.0    # 累计分红/利息（derived）
```

- [ ] **Step 3: 给 `Transaction` 表加 holding_id**

在 `Transaction` 类的 `platform_id` 字段之后加：

```python
    holding_id: Optional[int] = Field(default=None, foreign_key="holding.id", index=True)
```

- [ ] **Step 4: 给 `HoldingCreate` 加 source**

在 `HoldingCreate` 的 `cost_price` 之后加：

```python
    source: HoldingSource = HoldingSource.manual
```

- [ ] **Step 5: 给 `TransactionCreate` 与 `TransactionUpdate` 加 holding_id**

`TransactionCreate` 与 `TransactionUpdate` 各自在 `platform_id` 字段之后加：

```python
    holding_id: Optional[int] = None
```

- [ ] **Step 6: 验证导入无误**

Run: `cd backend && .venv/bin/python -c "import models; print(models.HoldingSource.derived, models.Holding.__fields__['realized_pnl'])"`
Expected: 打印 `HoldingSource.derived ...`，无异常

- [ ] **Step 7: Commit**

```bash
cd "/Volumes/T7 Shield/Study/CS/FinancialSystem"
find . -name '._*' -delete
git add backend/models.py
git commit -m "feat(models): add source/status/realized fields to Holding, holding_id to Transaction"
```

---

## Task 2: 核心派生算法（纯逻辑，TDD 重点）

**Files:**
- Create: `backend/position.py`
- Create: `backend/tests/test_position.py`

- [ ] **Step 1: 写失败测试（多笔加仓 → 移动加权均价）**

Create `backend/tests/test_position.py`：

```python
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
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_position.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'position'`

- [ ] **Step 3: 写最小实现**

Create `backend/position.py`：

```python
"""持仓派生计算：交易流水驱动 derived 持仓的数量 / 移动加权成本 / 已实现盈亏。

设计：纯逻辑 replay_transactions（无副作用，便于单测）与带 DB 副作用的
recompute_holding 分离。详见 docs/superpowers/specs/2026-06-15-transaction-driven-holdings-design.md
"""
from typing import Iterable

from models import Transaction, TxnAction

CLOSE_EPS = 1e-9  # 数量小于此阈值视为清仓，避免浮点残留


class PositionState:
    def __init__(self) -> None:
        self.quantity = 0.0
        self.avg_cost = 0.0
        self.realized_pnl = 0.0
        self.realized_income = 0.0


def replay_transactions(txns: Iterable[Transaction]) -> PositionState:
    """按 (date, id) 升序重放流水，返回派生状态。买/卖驱动数量与成本，
    分红计入已实现收益，入金/出金/其它跳过。"""
    st = PositionState()
    for t in sorted(txns, key=lambda x: (x.date or "", x.id or 0)):
        q = t.quantity or 0.0
        price = t.price or 0.0
        fee = t.fee or 0.0
        if t.action == TxnAction.buy:
            total_cost = st.quantity * st.avg_cost + q * price + fee
            st.quantity += q
            st.avg_cost = total_cost / st.quantity if st.quantity > CLOSE_EPS else 0.0
        elif t.action == TxnAction.sell:
            st.realized_pnl += q * price - q * st.avg_cost - fee
            st.quantity -= q
            if abs(st.quantity) < CLOSE_EPS:
                st.quantity = 0.0
                st.avg_cost = 0.0
        elif t.action == TxnAction.dividend:
            st.realized_income += t.amount if t.amount is not None else 0.0
        # deposit / withdraw / other: 不影响持仓
    return st
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/test_position.py -q`
Expected: PASS（1 passed）

- [ ] **Step 5: 加更多失败测试（部分卖出、清仓、手续费、卖超）**

在 `backend/tests/test_position.py` 末尾追加：

```python
def test_partial_sell_realizes_pnl_and_keeps_avg_cost():
    st = replay_transactions([_buy("2026-01-01", 200, 15), _sell("2026-02-01", 100, 25)])
    assert st.quantity == 100
    assert st.avg_cost == 15.0                     # 均价不变
    assert st.realized_pnl == 100 * (25 - 15)      # = 1000


def test_full_sell_closes_position():
    st = replay_transactions([_buy("2026-01-01", 100, 10), _sell("2026-02-01", 100, 12)])
    assert st.quantity == 0.0
    assert st.avg_cost == 0.0
    assert st.realized_pnl == 100 * (12 - 10)      # = 200


def test_fee_added_on_buy_subtracted_on_sell():
    st = replay_transactions([_buy("2026-01-01", 100, 10, fee=5), _sell("2026-02-01", 50, 10, fee=3)])
    # 买入成本 = 100*10 + 5 = 1005 → 均价 10.05
    assert round(st.avg_cost, 4) == 10.05
    # 已实现 = 50*10 - 50*10.05 - 3 = -500 - 2.5 - 3... = 50*10 - 50*10.05 - 3
    assert round(st.realized_pnl, 4) == round(50 * 10 - 50 * 10.05 - 3, 4)


def test_dividend_counts_as_income_only():
    div = Transaction(id=None, date="2026-03-01", action=TxnAction.dividend, amount=88.0)
    st = replay_transactions([_buy("2026-01-01", 100, 10), div])
    assert st.quantity == 100
    assert st.avg_cost == 10.0
    assert st.realized_income == 88.0


def test_oversell_yields_negative_quantity_anomaly():
    st = replay_transactions([_buy("2026-01-01", 100, 10), _sell("2026-02-01", 150, 12)])
    assert st.quantity < 0          # 负数量即异常信号，由上层标记，不抛错
```

- [ ] **Step 6: 运行全部，确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/test_position.py -q`
Expected: PASS（6 passed）

- [ ] **Step 7: Commit**

```bash
cd "/Volumes/T7 Shield/Study/CS/FinancialSystem"
find . -name '._*' -delete
git add backend/position.py backend/tests/test_position.py
git commit -m "feat(position): pure replay_transactions with weighted-average cost + realized pnl"
```

---

## Task 3: recompute_holding（带 DB 副作用）+ resolve_derived_holding

**Files:**
- Modify: `backend/position.py`
- Modify: `backend/tests/test_position.py`

- [ ] **Step 1: 写失败测试（recompute 回写 + 清仓置 closed）**

在 `backend/tests/test_position.py` 顶部 import 后追加：

```python
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool
from models import Holding, HoldingSource, HoldingStatus, Platform, User
from position import recompute_holding


def _mem_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    return Session(engine)


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
    assert h.quantity == 5        # manual 不被改动
    assert h.cost_price == 3
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_position.py -q`
Expected: FAIL，`ImportError: cannot import name 'recompute_holding'`

- [ ] **Step 3: 实现 recompute_holding + resolve_derived_holding**

在 `backend/position.py` 末尾追加（并把 import 行补全）：

```python
from typing import Optional

from sqlmodel import Session, select

from models import Currency, Holding, HoldingSource, HoldingStatus, User


def recompute_holding(session: Session, holding_id: int) -> None:
    """重放该持仓的全部流水并回写。manual 持仓直接跳过。"""
    holding = session.get(Holding, holding_id)
    if holding is None or holding.source != HoldingSource.derived:
        return
    txns = session.exec(
        select(Transaction).where(Transaction.holding_id == holding_id)
    ).all()
    st = replay_transactions(txns)
    holding.quantity = st.quantity
    holding.cost_price = st.avg_cost if st.quantity > CLOSE_EPS else None
    holding.realized_pnl = st.realized_pnl
    holding.realized_income = st.realized_income
    holding.status = (
        HoldingStatus.closed if abs(st.quantity) < CLOSE_EPS else HoldingStatus.open
    )
    session.add(holding)
    session.commit()


def resolve_derived_holding(
    session: Session,
    user: User,
    platform_id: Optional[int],
    symbol: str,
    currency: Currency,
    name: str = "",
    create_if_missing: bool = False,
) -> Optional[Holding]:
    """按 (user, platform, symbol, currency) 找 derived 持仓；
    create_if_missing 时不存在则新建一条。返回持仓或 None。"""
    if not symbol or platform_id is None:
        return None
    holding = session.exec(
        select(Holding).where(
            Holding.user_id == user.id,
            Holding.platform_id == platform_id,
            Holding.symbol == symbol,
            Holding.currency == currency,
            Holding.source == HoldingSource.derived,
        )
    ).first()
    if holding is None and create_if_missing:
        holding = Holding(
            user_id=user.id,
            platform_id=platform_id,
            currency=currency,
            symbol=symbol,
            name=name,
            source=HoldingSource.derived,
            status=HoldingStatus.open,
        )
        session.add(holding)
        session.commit()
        session.refresh(holding)
    return holding
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/test_position.py -q`
Expected: PASS（8 passed）

- [ ] **Step 5: Commit**

```bash
cd "/Volumes/T7 Shield/Study/CS/FinancialSystem"
find . -name '._*' -delete
git add backend/position.py backend/tests/test_position.py
git commit -m "feat(position): recompute_holding + resolve_derived_holding with DB side effects"
```

---

## Task 4: 数据库迁移（给存量表补列）

**Files:**
- Modify: `backend/database.py`

- [ ] **Step 1: 扩展迁移的 wanted 字典**

在 `backend/database.py` 的 `_migrate_add_user_id` 函数里，把 `wanted` 字典替换为：

```python
    wanted = {
        "platform": {"user_id": "INTEGER"},
        "holding": {
            "user_id": "INTEGER",
            "source": "VARCHAR DEFAULT 'manual'",
            "status": "VARCHAR DEFAULT 'open'",
            "realized_pnl": "FLOAT DEFAULT 0",
            "realized_income": "FLOAT DEFAULT 0",
        },
        "note": {"user_id": "INTEGER"},
        "snapshot": {"user_id": "INTEGER", "day": "VARCHAR"},
        "transaction": {"holding_id": "INTEGER"},
    }
```

> 注：SQLite `ADD COLUMN ... DEFAULT` 会把存量行填为默认值，老持仓即变 `manual/open`，行为不变。`transaction` 是 SQL 保留字，`PRAGMA table_info(transaction)` 与 `ALTER TABLE transaction` 在 SQLite 中可正常执行（实测放行）。

- [ ] **Step 2: 验证迁移对已有库幂等可跑**

Run: `cd backend && .venv/bin/python -c "from database import init_db; init_db(); print('migrated ok')"`
Expected: 打印 `migrated ok`，无异常（对本地已存在的 data.db 补列）

- [ ] **Step 3: 验证补列成功**

Run: `cd backend && .venv/bin/python -c "import sqlite3; c=sqlite3.connect('data.db'); print([r[1] for r in c.execute('PRAGMA table_info(holding)')]); print([r[1] for r in c.execute('PRAGMA table_info(\"transaction\")')])"`
Expected: holding 列含 `source status realized_pnl realized_income`；transaction 列含 `holding_id`

- [ ] **Step 4: Commit**

```bash
cd "/Volumes/T7 Shield/Study/CS/FinancialSystem"
find . -name '._*' -delete
git add backend/database.py
git commit -m "feat(db): migrate holding/transaction tables for derived-holding fields"
```

---

## Task 5: 交易路由驱动持仓

**Files:**
- Modify: `backend/routers/transactions.py`
- Create: `backend/tests/test_transactions_drive_holdings.py`

- [ ] **Step 1: 写失败的集成测试**

Create `backend/tests/test_transactions_drive_holdings.py`：

```python
def _platform(client):
    r = client.post("/api/platforms", json={"name": "Futu"})
    assert r.status_code == 200
    return r.json()["id"]


def test_buy_creates_derived_holding(client):
    pid = _platform(client)
    r = client.post("/api/transactions", json={
        "platform_id": pid, "date": "2026-01-01", "action": "buy",
        "symbol": "AAPL", "name": "Apple", "currency": "USD",
        "quantity": 100, "price": 10,
    })
    assert r.status_code == 200
    holdings = client.get("/api/holdings").json()
    derived = [h for h in holdings if h["source"] == "derived"]
    assert len(derived) == 1
    assert derived[0]["quantity"] == 100
    assert derived[0]["cost_price"] == 10


def test_second_buy_updates_average_cost(client):
    pid = _platform(client)
    base = {"platform_id": pid, "action": "buy", "symbol": "AAPL", "currency": "USD"}
    client.post("/api/transactions", json={**base, "date": "2026-01-01", "quantity": 100, "price": 10})
    client.post("/api/transactions", json={**base, "date": "2026-01-02", "quantity": 100, "price": 20})
    derived = [h for h in client.get("/api/holdings").json() if h["source"] == "derived"][0]
    assert derived["quantity"] == 200
    assert derived["cost_price"] == 15


def test_delete_transaction_recomputes(client):
    pid = _platform(client)
    base = {"platform_id": pid, "action": "buy", "symbol": "AAPL", "currency": "USD"}
    r1 = client.post("/api/transactions", json={**base, "date": "2026-01-01", "quantity": 100, "price": 10})
    client.post("/api/transactions", json={**base, "date": "2026-01-02", "quantity": 100, "price": 20})
    client.delete(f"/api/transactions/{r1.json()['id']}")
    derived = [h for h in client.get("/api/holdings").json() if h["source"] == "derived"][0]
    assert derived["quantity"] == 100
    assert derived["cost_price"] == 20
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_transactions_drive_holdings.py -q`
Expected: FAIL（derived 持仓未创建 / 数量不对）

- [ ] **Step 3: 改造交易路由**

把 `backend/routers/transactions.py` 的 import 段加入：

```python
from models import Currency, Holding, TxnAction
from position import recompute_holding, resolve_derived_holding
```

新增一个内部助手（放在 `_owned` 之后）：

```python
def _attach_and_recompute(session: Session, txn: Transaction, user: User) -> None:
    """为买/卖流水绑定 derived 持仓（买入可自动建仓）并触发重算。"""
    if txn.action not in (TxnAction.buy, TxnAction.sell):
        return
    if txn.holding_id is None:
        holding = resolve_derived_holding(
            session, user, txn.platform_id, txn.symbol, txn.currency,
            name=txn.name, create_if_missing=(txn.action == TxnAction.buy),
        )
        if holding is None:
            return
        txn.holding_id = holding.id
        session.add(txn)
        session.commit()
    recompute_holding(session, txn.holding_id)
```

把 `create_transaction` 的结尾改为（在 `session.refresh(txn)` 之后、`return` 之前插入）：

```python
    _attach_and_recompute(session, txn, user)
    session.refresh(txn)
```

把 `update_transaction` 改为：在循环 setattr 之前先记录旧持仓 id，提交后对新旧持仓都重算。完整替换函数体的提交段为：

```python
    old_holding_id = txn.holding_id
    for key, value in values.items():
        setattr(txn, key, value)
    session.add(txn)
    session.commit()
    session.refresh(txn)
    _attach_and_recompute(session, txn, user)
    if old_holding_id is not None and old_holding_id != txn.holding_id:
        recompute_holding(session, old_holding_id)
    session.refresh(txn)
    return txn
```

把 `delete_transaction` 改为：删除前记下 holding_id，删除后重算：

```python
    holding_id = txn.holding_id
    session.delete(txn)
    session.commit()
    if holding_id is not None:
        recompute_holding(session, holding_id)
    return {"ok": True}
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/test_transactions_drive_holdings.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
cd "/Volumes/T7 Shield/Study/CS/FinancialSystem"
find . -name '._*' -delete
git add backend/routers/transactions.py backend/tests/test_transactions_drive_holdings.py
git commit -m "feat(transactions): drive derived holdings on create/update/delete"
```

---

## Task 6: 持仓路由（include_closed + derived 只读保护 + source）

**Files:**
- Modify: `backend/routers/holdings.py`
- Modify: `backend/tests/test_transactions_drive_holdings.py`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_transactions_drive_holdings.py` 末尾追加：

```python
def test_closed_holding_hidden_by_default(client):
    pid = _platform(client)
    base = {"platform_id": pid, "symbol": "AAPL", "currency": "USD"}
    client.post("/api/transactions", json={**base, "action": "buy", "date": "2026-01-01", "quantity": 100, "price": 10})
    client.post("/api/transactions", json={**base, "action": "sell", "date": "2026-02-01", "quantity": 100, "price": 12})
    assert all(h["status"] != "closed" for h in client.get("/api/holdings").json())
    with_closed = client.get("/api/holdings?include_closed=true").json()
    assert any(h["status"] == "closed" for h in with_closed)


def test_derived_holding_rejects_manual_quantity_edit(client):
    pid = _platform(client)
    client.post("/api/transactions", json={
        "platform_id": pid, "action": "buy", "date": "2026-01-01",
        "symbol": "AAPL", "currency": "USD", "quantity": 100, "price": 10})
    hid = [h for h in client.get("/api/holdings").json() if h["source"] == "derived"][0]["id"]
    r = client.put(f"/api/holdings/{hid}", json={"quantity": 999})
    assert r.status_code == 400
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_transactions_drive_holdings.py -q`
Expected: FAIL（closed 仍返回 / PUT 未拦截）

- [ ] **Step 3: 改 list_holdings 支持 include_closed 并默认隐藏 closed**

把 `backend/routers/holdings.py` 的 `list_holdings` 替换为：

```python
@router.get("", response_model=List[Holding])
def list_holdings(
    platform_id: Optional[int] = Query(None),
    currency: Optional[Currency] = Query(None),
    include_closed: bool = Query(False),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    stmt = select(Holding).where(Holding.user_id == user.id)
    if platform_id is not None:
        stmt = stmt.where(Holding.platform_id == platform_id)
    if currency is not None:
        stmt = stmt.where(Holding.currency == currency)
    if not include_closed:
        stmt = stmt.where(Holding.status != HoldingStatus.closed)
    return session.exec(stmt).all()
```

并在 import 段加入 `HoldingStatus`、`HoldingSource`：

```python
from models import (
    Currency, Holding, HoldingCreate, HoldingSource, HoldingStatus,
    HoldingUpdate, Platform, User,
)
```

- [ ] **Step 4: 在 update_holding 里拦截 derived 改数量/成本**

把 `update_holding` 中 `values = data.model_dump(exclude_unset=True)` 之后加：

```python
    if holding.source == HoldingSource.derived and (
        "quantity" in values or "cost_price" in values
    ):
        raise HTTPException(400, "该持仓由交易流水驱动，请通过交易记录修改数量/成本")
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/ -q`
Expected: PASS（全部通过）

- [ ] **Step 6: Commit**

```bash
cd "/Volumes/T7 Shield/Study/CS/FinancialSystem"
find . -name '._*' -delete
git add backend/routers/holdings.py backend/tests/test_transactions_drive_holdings.py
git commit -m "feat(holdings): include_closed filter + derived read-only protection"
```

---

## Task 7: 汇总路由收益拆分

**Files:**
- Modify: `backend/routers/summary.py`
- Modify: `backend/tests/test_transactions_drive_holdings.py`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_transactions_drive_holdings.py` 末尾追加：

```python
def test_summary_exposes_realized_split(client):
    pid = _platform(client)
    base = {"platform_id": pid, "symbol": "AAPL", "currency": "USD"}
    client.post("/api/transactions", json={**base, "action": "buy", "date": "2026-01-01", "quantity": 100, "price": 10})
    client.post("/api/transactions", json={**base, "action": "sell", "date": "2026-02-01", "quantity": 100, "price": 12})
    s = client.get("/api/summary?currency=USD").json()
    assert "realized_pnl" in s and "realized_income" in s and "total_return" in s
    assert round(s["realized_pnl"], 2) == 200.0
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_transactions_drive_holdings.py::test_summary_exposes_realized_split -q`
Expected: FAIL（KeyError / 缺字段）

- [ ] **Step 3: 在 summary 累加已实现并加入返回**

在 `backend/routers/summary.py` 的循环里，`profit_cny += ...` 之后（仍在 `for h in holdings:` 内）加：

```python
        realized_pnl_cny += (h.realized_pnl or 0.0) * rate
        realized_income_cny += (h.realized_income or 0.0) * rate
```

在循环前初始化（与 `profit_cny = 0.0` 同处）：

```python
    realized_pnl_cny = 0.0
    realized_income_cny = 0.0
```

在 `total_profit = to_display(profit_cny)` 之后加：

```python
    realized_pnl = to_display(realized_pnl_cny)
    realized_income = to_display(realized_income_cny)
    total_return = total_profit + realized_pnl + realized_income
```

在最终 `return {...}` 字典里，`"profit_pct": ...` 之后加：

```python
        "realized_pnl": round(realized_pnl, 2),
        "realized_income": round(realized_income, 2),
        "total_return": round(total_return, 2),
```

> 注：`closed` 持仓市值为 0，不影响 total/未实现，但其 `realized_pnl` 仍被累加——符合"清仓收益留底"。`list` 查询此处用的是全量 holdings（summary 未过滤 status），故 closed 的 realized 也计入。

- [ ] **Step 4: 运行全部测试，确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/ -q`
Expected: PASS（全部通过）

- [ ] **Step 5: Commit**

```bash
cd "/Volumes/T7 Shield/Study/CS/FinancialSystem"
find . -name '._*' -delete
git add backend/routers/summary.py backend/tests/test_transactions_drive_holdings.py
git commit -m "feat(summary): expose realized_pnl / realized_income / total_return"
```

---

## Task 8: 备份兼容（导出加新字段 + 导入映射 holding_id + 重算 + 旧备份容错）

> 现状（已读 `backup.py`）：导入用 `dict.get(默认值)`，**旧备份本就不会崩**；但导出**未含**
> `source/status/realized_*` 与交易的 `holding_id`，导入也没做 holding 引用映射 →
> 新模型下导出再导入会把 derived 退化为 manual、交易关联断裂。本任务补全往返保真。

**Files:**
- Modify: `backend/routers/backup.py`
- Modify: `backend/tests/test_transactions_drive_holdings.py`

- [ ] **Step 1: 写失败测试（往返保真 + 旧备份容错）**

在 `backend/tests/test_transactions_drive_holdings.py` 末尾追加：

```python
def test_backup_roundtrip_preserves_derived(client):
    pid = _platform(client)
    client.post("/api/transactions", json={
        "platform_id": pid, "action": "buy", "date": "2026-01-01",
        "symbol": "AAPL", "name": "Apple", "currency": "USD",
        "quantity": 100, "price": 10})
    dump = client.get("/api/backup").json()
    assert dump["holdings"][0]["source"] == "derived"          # 导出含 source
    assert dump["transactions"][0]["holding_ref"] is not None   # 导出含 holding 引用

    r = client.post("/api/backup/import", json=dump)
    assert r.status_code == 200
    derived = [h for h in client.get("/api/holdings").json() if h["source"] == "derived"]
    assert len(derived) == 1
    assert derived[0]["quantity"] == 100      # 重算后数量正确
    assert derived[0]["cost_price"] == 10


def test_import_legacy_backup_without_new_fields(client):
    # 旧备份：holding 无 source/status/realized_*、ref；transaction 无 holding_ref
    legacy = {
        "platforms": [{"ref": 1, "name": "OldP", "note": None}],
        "holdings": [{
            "platform_ref": 1, "currency": "CNY", "asset_type": "cash",
            "market": "NONE", "symbol": "", "name": "现金",
            "quantity": None, "manual_value": 1000, "cost_price": None,
        }],
        "transactions": [],
        "notes": [],
    }
    r = client.post("/api/backup/import", json=legacy)
    assert r.status_code == 200
    holds = client.get("/api/holdings").json()
    assert len(holds) == 1
    assert holds[0]["source"] == "manual"        # 缺省为 manual
    assert holds[0]["manual_value"] == 1000
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_transactions_drive_holdings.py::test_backup_roundtrip_preserves_derived -q`
Expected: FAIL（导出 dict 无 `source`/`holding_ref` 键 → KeyError）

- [ ] **Step 3: 导出补新字段**

在 `backend/routers/backup.py` 的 `export_backup` 里，holdings 列表推导的每个 dict（`"prev_close": h.prev_close,` 之后）加：

```python
                "ref": h.id,
                "source": h.source.value,
                "status": h.status.value,
                "realized_pnl": h.realized_pnl,
                "realized_income": h.realized_income,
```

transactions 列表推导的每个 dict（`"amount": t.amount,` 之后）加：

```python
                "holding_ref": t.holding_id,
```

- [ ] **Step 4: 导入重建持仓时带新字段并记录 holding 引用映射**

把 `import_backup` 里"# 3) 重建持仓"整段替换为：

```python
    # 3) 重建持仓，记录 旧holding ref -> 新id
    hold_map: Dict[Any, int] = {}
    for h in data.holdings:
        pid = ref_map.get(h.get("platform_ref"))
        if pid is None:
            continue  # 平台缺失则跳过该持仓
        holding = Holding(
            user_id=user.id, platform_id=pid,
            currency=h.get("currency", "CNY"), asset_type=h.get("asset_type", "stock"),
            market=h.get("market", "A"), symbol=h.get("symbol", ""), name=h.get("name", ""),
            quantity=h.get("quantity"), manual_value=h.get("manual_value"),
            cost_price=h.get("cost_price"), current_price=h.get("current_price"),
            prev_close=h.get("prev_close"),
            source=h.get("source", "manual"), status=h.get("status", "open"),
            realized_pnl=h.get("realized_pnl", 0.0),
            realized_income=h.get("realized_income", 0.0),
        )
        session.add(holding)
        session.commit()
        session.refresh(holding)
        if h.get("ref") is not None:
            hold_map[h.get("ref")] = holding.id
```

- [ ] **Step 5: 导入交易时映射 holding_id**

把"# 4) 重建交易"里 `Transaction(...)` 构造的 `platform_id=ref_map.get(t.get("platform_ref")),` 这一行之后加一行：

```python
            holding_id=hold_map.get(t.get("holding_ref")),
```

- [ ] **Step 6: 导入结尾对 derived 持仓全量重算**

在 `import_backup` 末尾 `session.commit()`（第 5 步重建心得之后那个）与 `return {...}` 之间插入：

```python
    # 6) derived 持仓按导入的交易重算数量/成本/已实现（manual 持仓会被 recompute 跳过）
    from position import recompute_holding
    for hid in hold_map.values():
        recompute_holding(session, hid)
```

- [ ] **Step 7: 运行全部测试，确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/ -q`
Expected: PASS（全部通过）

- [ ] **Step 8: Commit**

```bash
cd "/Volumes/T7 Shield/Study/CS/FinancialSystem"
find . -name '._*' -delete
git add backend/routers/backup.py backend/tests/test_transactions_drive_holdings.py
git commit -m "feat(backup): round-trip derived holdings (export fields + remap + recompute)"
```

---

## Task 9: 全量回归 + 文档同步

**Files:**
- Modify: `backend/ARCHITECTURE.md` 之外的根 `ARCHITECTURE.md`、`CHANGELOG.md`

- [ ] **Step 1: 跑全部后端测试**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: 全部 PASS

- [ ] **Step 2: 手动起服务冒烟（确认线上同款迁移不崩）**

Run: `cd "/Volumes/T7 Shield/Study/CS/FinancialSystem" && python3 dev.py start`，浏览器进 localhost:5173 登录后随意加一笔买入交易，确认不报错；Ctrl+C 停止。
Expected: 应用正常、加交易无 500

- [ ] **Step 3: 更新 CHANGELOG.md**

在 `CHANGELOG.md` 顶部记录区追加一条（类型 ✨新增）：交易驱动持仓后端引擎；说明 derived/manual 混合、移动加权、已实现盈亏拆分、零风险迁移；注意事项：重启后端自动迁移补列，存量数据默认 manual 不变。

- [ ] **Step 4: 更新 ARCHITECTURE.md**

在数据模型小节补充 Holding 的 `source/status/realized_pnl/realized_income`、Transaction 的 `holding_id`，以及新增 `position.py` 模块（派生计算）。

- [ ] **Step 5: Commit**

```bash
cd "/Volumes/T7 Shield/Study/CS/FinancialSystem"
find . -name '._*' -delete
git add CHANGELOG.md ARCHITECTURE.md
git commit -m "docs: record transaction-driven holdings backend"
```

---

## 完成标准

- `cd backend && .venv/bin/python -m pytest -q` 全绿
- 加买入交易自动建 derived 持仓、数量/成本正确；多笔加仓走移动加权；卖出结转已实现盈亏；清仓置 closed 并默认隐藏
- derived 持仓 PUT 改数量/成本被 400 拦截
- summary 返回 realized_pnl / realized_income / total_return
- 存量 manual 持仓行为与数字不变；旧备份可导入
- **前端 UX 在 Plan 2 实现**（本计划只动后端，现有前端不受影响）
