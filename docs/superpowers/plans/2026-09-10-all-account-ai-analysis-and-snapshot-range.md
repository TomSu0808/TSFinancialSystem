# 全账户 AI 分析与总资产走势时间范围 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在已有 portfolio-review 投研流程上增加「全账户 AI 分析」（首页总览摘要 + 完整报告 + 行动项）并给「总资产走势」曲线加 6 档时间范围切换。

**Architecture:** 后端新增 `portfolio_context.py` 统一构建全账户上下文（与 `/api/summary` 同 CNY 折算口径），`snapshots.py` 增加 `range` 参数与日历边界解析；`research_prompt_builder` 增加组合专用输出章节；前端 Dashboard 拆出独立曲线加载并加范围选择器，Research 页支持预选组合分析与可选偏好，首页读最新组合报告摘要。全程复用 `ResearchReport`、`input_context_md`、`prompt_md`、`report_md` 与行动项转笔记，不新增业务表。

**Tech Stack:** React 18 + Vite + Ant Design + ECharts（前端）；FastAPI + SQLModel（后端）；默认 SQLite 兼容 PostgreSQL；Pytest（后端）。

**Spec:** `0909开发需求.doc`（本计划据其第 1–6 节实现；需求 A = 全账户 AI 分析，需求 B = 总资产走势时间范围）。

## 2026-09-12 实现状态补充

原计划的步骤记录保留。实际代码已完成范围筛选、组合上下文、报告摘要与默认模型接线，并补充每日盈亏和登录刷新。
当前验收与限制以 [每日盈亏与全账户分析](../../daily-pnl-and-portfolio-analysis.md) 为准。
本地实现和验证已推进，线上发布仍需要有效 Fly.io 登录态；不将文档或代码完成等同于线上生效。

## Global Constraints

- 范围顺序固定：**最大 / 1年 / 半年 / 3个月 / 1个月 / 1周**；首次默认「半年」。
- `range` 枚举值：`max | 1y | 6m | 3m | 1m | 1w`；`days` 参数保留原默认值 90 与校验 `ge=1, le=3650`；两者同传时 `range` 优先，非法 `range` 返回 400。
- 返回字段保持 `day`、`total_cny`、`total_usd`，按日期升序，过滤无 `day` 旧记录，严格按用户隔离。
- 汇率口径：USD/CNY 取 `FxRate(pair="USDCNY")`；HKD 按 **7.8 HKD/USD** 近似折算并标注「估算」。
- 现金口径固定文案：现金账本由入金/出金重算，未完整联动证券买卖，**不可视为精确可用余额**，不据此给出精确调仓金额。
- 缺失价格/成本必须显式标注「缺失/未知」，不得解释为 0。
- **不新增业务表**：复用 `ResearchReport` 的 `input_context_md`/`prompt_md`/`report_md`/`status`；展示币种通过请求 schema 传入并写入 `input_context_md`，不新增持久化列。
- 组合专用输出要求仅作用于 `portfolio-review` 模板，单公司投研行为不变。
- 保护工作区已有修改，不覆盖用户文件，不擅自提交/推送/部署。

---

## File Structure

**Backend**
- Modify `backend/routers/snapshots.py` — 增加 `range` 参数 + `_range_start` 日历边界。
- Create `backend/portfolio_context.py` — 全账户上下文构建（统一折算 + 数据时点 + 集中度 + 笔记 + 数据质量）。
- Modify `backend/research_prompt_builder.py` — `build_prompt` 增加 `is_portfolio` 与组合专用输出章节。
- Modify `backend/models.py` — `ResearchRunCreate` 增加 `display_currency`。
- Modify `backend/research_service.py` — `create_run` 使用新上下文、传 `is_portfolio` 与 `display_currency`。
- Modify `backend/routers/research.py` — `/runs` 透传 `display_currency`；新增 `GET /research/portfolio-summary`；`_extract_action_items` 泛化复用。
- Create `backend/tests/test_snapshots_range.py`、`backend/tests/test_portfolio_context.py`；扩展 `backend/tests/test_research_tracking.py`。

**Frontend**
- Modify `frontend/src/api/index.js` — `getSnapshots` 改收 `params`；新增 `getPortfolioSummary`。
- Modify `frontend/src/pages/Dashboard.jsx` — 曲线范围选择器 + 独立加载 + 单点/空态 + 「AI 分析全部账户」入口 + 总览摘要卡片。
- Modify `frontend/src/pages/Research.jsx` — 预选 portfolio-review + 展示币种 + 可选偏好字段 + 报告深链。

---

## Task 1: 快照范围参数与日历边界（后端）

**Files:**
- Modify: `backend/routers/snapshots.py`
- Test: `backend/tests/test_snapshots_range.py`（新建）

**Interfaces:**
- Consumes: `Snapshot`（`models.Snapshot`：`user_id`、`day`、`total_cny`、`total_usd`）。
- Produces: `_range_start(range_key: str, today: date) -> Optional[str]`（返回含起始日 `YYYY-MM-DD`，`max` 返回 `None`）；`GET /api/snapshots?range=<key>` 返回 `[{"day","total_cny","total_usd"}]`。

- [ ] **Step 1: 写 `_range_start` 单元测试（先测纯函数）**

Create `backend/tests/test_snapshots_range.py`:

```python
"""快照 range 参数与日历边界测试。"""
from datetime import date

from routers.snapshots import _range_start


def test_range_start_month_end_and_leap():
    assert _range_start("1m", date(2026, 3, 31)) == "2026-02-28"
    assert _range_start("1m", date(2024, 3, 31)) == "2024-02-29"   # 闰年 2 月 29
    assert _range_start("1y", date(2024, 2, 29)) == "2023-02-28"   # 闰日回溯 1 年
    assert _range_start("3m", date(2026, 5, 31)) == "2026-02-28"
    assert _range_start("6m", date(2026, 8, 31)) == "2026-02-28"


def test_range_start_week_and_max():
    assert _range_start("1w", date(2026, 1, 10)) == "2026-01-04"  # 今天及之前 6 天 = 7 天
    assert _range_start("max", date(2026, 1, 1)) is None
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv-mac-py39/bin/python -m pytest tests/test_snapshots_range.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'routers.snapshots'` 或 `ImportError: cannot import name '_range_start'`（因为尚未实现）。

- [ ] **Step 3: 实现 `_range_start` 与 `list_snapshots` 改造**

Modify `backend/routers/snapshots.py` — 完整替换为：

```python
"""净值快照查询：供总资产走势图（按用户隔离）。"""
import calendar
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from auth import get_current_user
from database import get_session
from models import Snapshot, User

router = APIRouter(prefix="/api/snapshots", tags=["snapshots"])

RANGE_KEYS = ("max", "1y", "6m", "3m", "1m", "1w")
_RANGE_MONTHS = {"1m": 1, "3m": 3, "6m": 6, "1y": 12}


def _back_months(today: date, months: int) -> date:
    m = today.month - 1 - months
    y = today.year + m // 12
    mm = m % 12 + 1
    last = calendar.monthrange(y, mm)[1]
    return date(y, mm, min(today.day, last))


def _range_start(range_key: str, today: date) -> Optional[str]:
    """返回区间起始日（含）；max 返回 None 表示无下限（最早有效快照）。"""
    if range_key == "max":
        return None
    if range_key == "1w":
        return (today - timedelta(days=6)).isoformat()
    return _back_months(today, _RANGE_MONTHS[range_key]).isoformat()


@router.get("")
def list_snapshots(
    days: int = Query(90, ge=1, le=3650, description="取最近多少天（旧参数，保留兼容）"),
    range_key: Optional[str] = Query(None, alias="range", description="时间范围：max/1y/6m/3m/1m/1w"),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> List[dict]:
    today = datetime.utcnow().date()
    stmt = select(Snapshot).where(Snapshot.user_id == user.id)
    if range_key is not None:
        if range_key not in RANGE_KEYS:
            raise HTTPException(400, f"非法 range：{range_key}，可选 {', '.join(RANGE_KEYS)}")
        since = _range_start(range_key, today)
        if since is not None:
            stmt = stmt.where(Snapshot.day >= since)
    else:
        since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        stmt = stmt.where(Snapshot.day >= since)
    rows = session.exec(stmt.order_by(Snapshot.day)).all()
    return [
        {"day": r.day, "total_cny": round(r.total_cny, 2), "total_usd": round(r.total_usd, 2)}
        for r in rows
        if r.day  # 跳过历史无 day 的旧记录
    ]
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && .venv-mac-py39/bin/python -m pytest tests/test_snapshots_range.py -v`
Expected: PASS（两个 `_range_start` 测试通过）。

- [ ] **Step 5: 补端点集成测试**

Append to `backend/tests/test_snapshots_range.py`:

```python
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
```

- [ ] **Step 6: 运行全部快照测试**

Run: `cd backend && .venv-mac-py39/bin/python -m pytest tests/test_snapshots_range.py -v`
Expected: 全部 PASS。

- [ ] **Step 7: Commit**

```bash
git add backend/routers/snapshots.py backend/tests/test_snapshots_range.py
git commit -m "feat(snapshots): add range param (max/1y/6m/3m/1m/1w) with calendar boundaries"
```

---

## Task 2: 曲线范围选择器与独立加载（前端）

**Files:**
- Modify: `frontend/src/api/index.js`
- Modify: `frontend/src/pages/Dashboard.jsx`

**Interfaces:**
- Consumes: `GET /api/snapshots?range=<key>`（Task 1）。
- Produces: `getSnapshots(params)` 返回快照数组；Dashboard 曲线卡片支持 6 档切换、`localStorage['snapshotRange']` 记忆、独立 loading/error、过时请求忽略、单点与空态。

- [ ] **Step 1: 更新 api 封装**

Modify `frontend/src/api/index.js`，替换 `getSnapshots`（约 108–109 行）并新增 `getPortfolioSummary`：

```js
// ---- 净值走势 ----
export const getSnapshots = (params = {}) =>
  client.get('/snapshots', { params }).then((r) => r.data)

// ---- 全账户 AI 分析摘要 ----
export const getPortfolioSummary = () =>
  client.get('/research/portfolio-summary').then((r) => r.data)
```

- [ ] **Step 2: Dashboard 导入与状态**

Modify `frontend/src/pages/Dashboard.jsx`：
1. antd 导入行加 `Radio`（当前行 4 是 `Alert, Button, Card, Col, Divider, Empty, Row, Segmented, Space, Steps, Tag, Tooltip, Typography, message,`）。
2. `import { getSummary, getSnapshots, refreshPrices, refreshRate, getAutomationStatus, runNow, listAlertEvents, getPortfolioSummary } from '../api'`。
3. 在组件状态区（`const [runningNow, setRunningNow] = useState(false)` 之后）加：

```jsx
const RANGE_OPTIONS = [
  { value: 'max', label: '最大' },
  { value: '1y', label: '1年' },
  { value: '6m', label: '半年' },
  { value: '3m', label: '3个月' },
  { value: '1m', label: '1个月' },
  { value: '1w', label: '1周' },
]
const [snapRange, setSnapRange] = useState(() => localStorage.getItem('snapshotRange') || '6m')
const [snapsLoading, setSnapsLoading] = useState(false)
const [snapsError, setSnapsError] = useState(null)
const [portfolioSummary, setPortfolioSummary] = useState(null)
const snapSeq = useRef(0)
const snapRangeRef = useRef(snapRange)
```

- [ ] **Step 3: 独立快照加载（含过时请求忽略）**

替换现有 `load`（44–58 行）并新增 `loadSnapshots`。用以下代码替换 `const load = useCallback(...)` 整段：

```jsx
const loadSnapshots = useCallback(async (range) => {
  const seq = ++snapSeq.current
  setSnapsLoading(true)
  setSnapsError(null)
  try {
    const snaps = await getSnapshots({ range })
    if (seq === snapSeq.current) setSnapshots(snaps)
  } catch (e) {
    if (seq === snapSeq.current) setSnapsError(e.message)
  } finally {
    if (seq === snapSeq.current) setSnapsLoading(false)
  }
}, [])

const load = useCallback(async () => {
  setLoading(true)
  try {
    const s = await getSummary(displayCurrency)   // summary 会 upsert 当日快照
    setSummary(s)
  } catch (e) {
    message.error('加载汇总失败：' + e.message)
  } finally {
    setLoading(false)
  }
  await loadSnapshots(snapRangeRef.current)       // 快照必须在 summary 之后读取
  getAutomationStatus().then(setAutomationStatus).catch(() => {})
  listAlertEvents({ status: 'unread', limit: 3 }).then(setUnreadAlerts).catch(() => {})
  getPortfolioSummary().then(setPortfolioSummary).catch(() => {})
}, [displayCurrency, loadSnapshots])
```

替换 `useEffect`（60–62 行）为：

```jsx
useEffect(() => {
  load()
}, [load])

useEffect(() => {
  snapRangeRef.current = snapRange
  localStorage.setItem('snapshotRange', snapRange)
  loadSnapshots(snapRange)
}, [snapRange, loadSnapshots])
```

- [ ] **Step 4: 刷新后先快照更新再取曲线**

替换 `doRefresh` 中 `await load()`（76 行）保持 `load()` 不变即可 —— `load` 已保证 `getSummary` → `loadSnapshots` 顺序（`getSummary` 在 `/api/summary` 内 `_upsert_daily_snapshot` 写当日快照后再读曲线）。无需额外改动，确认 `doRefresh` 仍调用 `await load()`。

- [ ] **Step 5: 曲线卡片加范围选择器与空/单点态**

替换「总资产走势」Card（580–586 行）为：

```jsx
<Card
  loading={loading || snapsLoading}
  title="总资产走势"
  extra={
    <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
      <Radio.Group
        size="small"
        optionType="button"
        buttonStyle="solid"
        value={snapRange}
        onChange={(e) => setSnapRange(e.target.value)}
        options={RANGE_OPTIONS}
      />
    </div>
  }
>
  {snapsError ? (
    <Empty description={`走势加载失败：${snapsError}`} />
  ) : snapshots.length === 0 ? (
    <Empty description="该时间范围内暂无净值记录" />
  ) : (
    <>
      <ReactECharts option={trendOption} style={{ height: 320 }} notMerge />
      <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 6 }}>
        {snapshots.length === 1
          ? `仅有 1 个净值点（${snapshots[0].day}）`
          : `实际数据范围：${snapshots[0].day} ~ ${snapshots[snapshots.length - 1].day}`}
      </Text>
    </>
  )}
</Card>
```

（`trendOption` 的 `showSymbol: snapshots.length < 30` 已保证单点/少量点显示点；无需改。）

- [ ] **Step 6: 构建验证**

Run: `cd frontend && npm run build`
Expected: 构建成功，无报错。

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/index.js frontend/src/pages/Dashboard.jsx
git commit -m "feat(dashboard): add snapshot range selector with independent loading"
```

---

## Task 3: 全账户上下文构建器（后端）

**Files:**
- Create: `backend/portfolio_context.py`
- Test: `backend/tests/test_portfolio_context.py`（新建）

**Interfaces:**
- Consumes: `models`（`Holding`、`Platform`、`FxRate`、`Note`、`Currency`、`HoldingStatus`、`market_value`、`cost_basis`、`profit`）。
- Produces: `build_account_context(session: Session, user: User, display_currency: Currency) -> str`（Markdown，供 Task 5 `create_run` 使用）；`get_to_cny_rates(session)` 可选复用。

- [ ] **Step 1: 写上下文构建测试**

Create `backend/tests/test_portfolio_context.py`:

```python
"""全账户组合上下文构建测试。"""
from datetime import datetime

from models import Currency, FxRate, Holding, Platform, User


def _mk(session, user, currency="CNY", market="A", symbol="600519", name="茅台",
         quantity=100.0, cost_price=100.0, current_price=100.0, status="open",
         realized_pnl=0.0, realized_income=0.0, platform=None):
    if platform is None:
        platform = Platform(user_id=user.id, name="默认平台")
        session.add(platform)
        session.commit()
        session.refresh(platform)
    h = Holding(
        user_id=user.id, platform_id=platform.id, currency=currency, market=market,
        symbol=symbol, name=name, quantity=quantity, cost_price=cost_price,
        current_price=current_price, status=status, realized_pnl=realized_pnl,
        realized_income=realized_income,
    )
    session.add(h)
    session.commit()
    session.refresh(h)
    return h, platform


def test_total_matches_summary_cny(client, session, user):
    """多币种总资产应与 /api/summary 的 CNY 口径一致。"""
    session.add(FxRate(pair="USDCNY", rate=7.0, updated_at=datetime.utcnow()))
    session.commit()
    _mk(session, user, currency="CNY", quantity=100, current_price=100)  # 10,000 CNY
    _mk(session, user, currency="USD", market="US", symbol="AAPL", name="Apple",
        quantity=100, current_price=100)  # 10,000 USD -> 70,000 CNY

    from portfolio_context import build_account_context
    ctx = build_account_context(session, user, Currency.CNY)
    assert "80,000" in ctx  # 10,000 + 70,000
    assert "展示币种：CNY" in ctx


def test_display_currency_usd(client, session, user):
    session.add(FxRate(pair="USDCNY", rate=7.0, updated_at=datetime.utcnow()))
    session.commit()
    _mk(session, user, currency="USD", market="US", symbol="AAPL", name="Apple",
        quantity=100, current_price=100)  # 10,000 USD

    from portfolio_context import build_account_context
    ctx = build_account_context(session, user, Currency.USD)
    assert "展示币种：USD" in ctx
    assert "10,000" in ctx  # 展示币种为 USD 时总资产≈10,000


def test_cross_account_same_symbol_merged(client, session, user):
    p1 = Platform(user_id=user.id, name="券商A"); session.add(p1); session.commit(); session.refresh(p1)
    p2 = Platform(user_id=user.id, name="券商B"); session.add(p2); session.commit(); session.refresh(p2)
    _mk(session, user, market="US", symbol="AAPL", name="Apple", quantity=10, current_price=100, platform=p1)
    _mk(session, user, market="US", symbol="AAPL", name="Apple", quantity=20, current_price=100, platform=p2)

    from portfolio_context import build_account_context
    ctx = build_account_context(session, user, Currency.CNY)
    assert "券商A" in ctx and "券商B" in ctx  # 保留账户明细
    assert "AAPL" in ctx  # 集中度合并后仍含该标的


def test_different_market_same_symbol_not_merged(client, session, user):
    _mk(session, user, market="A", symbol="0700", name="A股0700", quantity=10, current_price=10)
    _mk(session, user, market="HK", symbol="0700", name="腾讯", quantity=10, current_price=10)
    from portfolio_context import build_account_context
    ctx = build_account_context(session, user, Currency.CNY)
    assert "A股0700" in ctx and "腾讯" in ctx  # 两者都保留，未误合并


def test_closed_holding_realized_pnl_included(client, session, user):
    _mk(session, user, status="open", quantity=10, current_price=10)
    _mk(session, user, status="closed", symbol="CLOSED", name="已清仓",
        quantity=0, current_price=None, realized_pnl=500.0)
    from portfolio_context import build_account_context
    ctx = build_account_context(session, user, Currency.CNY)
    assert "已清仓" in ctx or "已清仓持仓" in ctx
    assert "500.00" in ctx  # 已实现盈亏含清仓收益


def test_missing_price_marked_not_zero(client, session, user):
    _mk(session, user, quantity=10, cost_price=50, current_price=None)  # 缺现价
    from portfolio_context import build_account_context
    ctx = build_account_context(session, user, Currency.CNY)
    assert "缺失" in ctx  # 现价/市值显式标注为缺失
    assert "未知（缺现价）" in ctx  # 盈亏不解释为 0 或 -100%


def test_missing_cost_marked_not_zero(client, session, user):
    _mk(session, user, quantity=10, cost_price=None, current_price=100)  # 缺成本价
    from portfolio_context import build_account_context
    ctx = build_account_context(session, user, Currency.CNY)
    assert "未知（缺成本）" in ctx  # 有现价但缺成本时标注


def test_missing_price_not_counted_as_aggregate_loss(client, session, user):
    _mk(session, user, quantity=10, cost_price=50, current_price=None)  # 缺现价，成本 500
    _mk(session, user, market="US", symbol="AAPL", name="Apple",
        quantity=10, current_price=100)  # 有价，盈亏为 0
    from portfolio_context import build_account_context
    ctx = build_account_context(session, user, Currency.CNY)
    assert "未知（缺现价）" in ctx  # 明细表标注
    assert "-500" not in ctx  # 聚合「未实现盈亏」不把缺价解释为 -100% 亏损


def test_hkd_display_currency(client, session, user):
    session.add(FxRate(pair="USDCNY", rate=7.8, updated_at=datetime.utcnow()))
    session.commit()
    _mk(session, user, currency="HKD", market="HK", symbol="0700", name="腾讯",
        quantity=100, current_price=100)  # 10,000 HKD
    from portfolio_context import build_account_context
    ctx = build_account_context(session, user, Currency.HKD)
    assert "展示币种：HKD" in ctx
    assert "10,000" in ctx  # HKD 展示按 HKD 汇率折算（非 USD 汇率）


def test_cash_and_hkd_disclaimers(client, session, user):
    session.add(FxRate(pair="USDCNY", rate=7.0, updated_at=datetime.utcnow()))
    session.commit()
    _mk(session, user, currency="HKD", market="HK", symbol="0700", name="腾讯",
        quantity=100, current_price=100)
    from portfolio_context import build_account_context
    ctx = build_account_context(session, user, Currency.CNY)
    assert "7.8" in ctx  # HKD 近似折算标注
    assert "入金" in ctx or "现金" in ctx  # 现金口径说明
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv-mac-py39/bin/python -m pytest tests/test_portfolio_context.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'portfolio_context'`。

- [ ] **Step 3: 实现 `portfolio_context.py`**

Create `backend/portfolio_context.py`:

```python
"""全账户组合分析上下文构建器。

与 /api/summary 使用同一 CNY 折算口径；数字由后端统一计算，缺失值显式标注，
不伪造。供 portfolio-review 投研使用。
"""
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlmodel import Session, select

from models import (
    Currency, FxRate, Holding, HoldingStatus, Note, Platform, User,
    cost_basis, market_value, profit,
)

HKD_PEG = 7.8


def get_to_cny_rates(session: Session) -> Tuple[Dict[Currency, float], float, str]:
    fx = session.exec(select(FxRate).where(FxRate.pair == "USDCNY")).first()
    usdcny = fx.rate if fx else 7.2
    fx_updated_at = fx.updated_at.isoformat() if fx and fx.updated_at else "unknown"
    to_cny = {
        Currency.CNY: 1.0,
        Currency.USD: usdcny,
        Currency.HKD: usdcny / HKD_PEG,
    }
    return to_cny, usdcny, fx_updated_at


def _valued(h: Holding) -> bool:
    """该持仓是否有可估值的市值（手填金额或 数量×现价）。"""
    return h.manual_value is not None or (h.quantity is not None and h.current_price is not None)


def _fmt(v: Optional[float], cur: str, digits: int = 2) -> str:
    return "未知" if v is None else f"{v:,.{digits}f} {cur}"


def build_account_context(session: Session, user: User, display_currency: Currency) -> str:
    to_cny, usdcny, fx_updated_at = get_to_cny_rates(session)
    holdings = list(session.exec(select(Holding).where(Holding.user_id == user.id)).all())
    platforms = {
        p.id: p.name
        for p in session.exec(select(Platform).where(Platform.user_id == user.id)).all()
    }

    if not holdings:
        return "\n**（当前无任何账户或持仓数据）**\n"

    open_holdings = [h for h in holdings if h.status == HoldingStatus.open]
    closed_holdings = [h for h in holdings if h.status == HoldingStatus.closed]

    rows = []
    total_cny = 0.0
    cost_cny = 0.0
    unrealized_cny = 0.0
    realized_pnl_cny = 0.0
    realized_income_cny = 0.0
    for h in holdings:
        rate = to_cny.get(h.currency, 1.0)
        mv_native = market_value(h)
        cb = cost_basis(h)
        pnl = profit(h)
        mv_cny = mv_native * rate
        cb_cny = cb * rate if cb is not None else None
        pnl_cny = pnl * rate if pnl is not None else None
        if h.status == HoldingStatus.open and _valued(h):
            total_cny += mv_cny
            if cb_cny is not None:
                cost_cny += cb_cny
                unrealized_cny += (pnl_cny or 0.0)
        realized_pnl_cny += (h.realized_pnl or 0.0) * rate
        realized_income_cny += (h.realized_income or 0.0) * rate
        rows.append({
            "h": h, "rate": rate, "mv_native": mv_native, "mv_cny": mv_cny,
            "cb_cny": cb_cny, "pnl": pnl, "pnl_cny": pnl_cny,
        })

    def to_display(cny: float) -> float:
        rate = to_cny.get(display_currency, 1.0)
        return cny / rate if rate else 0.0

    cur_label = display_currency.value

    by_account = defaultdict(float)
    by_type = defaultdict(float)
    by_currency_native = defaultdict(float)
    cash_cny = 0.0
    for r in rows:
        h = r["h"]
        if h.status != HoldingStatus.open:
            continue
        by_account[h.platform_id] += r["mv_cny"]
        by_type[h.asset_type.value] += r["mv_cny"]
        by_currency_native[h.currency.value] += r["mv_native"]
        if h.asset_type.value == "cash":
            cash_cny += r["mv_cny"]

    groups = defaultdict(lambda: {"mv_cny": 0.0, "accounts": set(), "h": None})
    for r in rows:
        h = r["h"]
        if h.status != HoldingStatus.open:
            continue
        if h.symbol and h.market.value != "NONE":
            g = groups[(h.market.value, h.symbol)]
            g["mv_cny"] += r["mv_cny"]
            g["accounts"].add(platforms.get(h.platform_id, f"#{h.platform_id}"))
            g["h"] = g["h"] or h
    top_symbols = sorted(groups.values(), key=lambda g: g["mv_cny"], reverse=True)

    lines: List[str] = []
    lines.append("## 分析时点与展示口径")
    lines.append(f"- 分析时点：{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"- 展示币种：{cur_label}")
    lines.append(f"- USD/CNY = {usdcny:.4f}；HKD/CNY ≈ {usdcny / HKD_PEG:.4f}（联系汇率≈7.8 HKD/USD，估算）")
    lines.append(f"- 汇率更新时间：{fx_updated_at}")

    lines.append("")
    lines.append("## 账户汇总")
    lines.append(f"- 总资产：{_fmt(to_display(total_cny), cur_label)}")
    lines.append(f"- 现金：{_fmt(to_display(cash_cny), cur_label)}")
    lines.append(f"- 未实现盈亏：{_fmt(to_display(unrealized_cny), cur_label)}")
    lines.append(f"- 已实现盈亏：{_fmt(to_display(realized_pnl_cny), cur_label)}（含已清仓持仓）")
    lines.append(f"- 分红/利息：{_fmt(to_display(realized_income_cny), cur_label)}")
    if closed_holdings:
        lines.append(f"- 已清仓持仓数：{len(closed_holdings)}（其已实现盈亏已并入上表，不列为当前持仓）")

    lines.append("")
    lines.append("## 账户与配置")
    lines.append("### 各账户")
    for pid, cny in sorted(by_account.items(), key=lambda kv: kv[1], reverse=True):
        lines.append(f"- {platforms.get(pid, f'#{pid}')}：{_fmt(to_display(cny), cur_label)}")
    lines.append("### 资产类型")
    for t, cny in sorted(by_type.items(), key=lambda kv: kv[1], reverse=True):
        lines.append(f"- {t}：{_fmt(to_display(cny), cur_label)}")
    lines.append("### 币种分布（原币种口径）")
    for c, native in sorted(by_currency_native.items(), key=lambda kv: kv[1], reverse=True):
        lines.append(f"- {c}：{_fmt(native, c)}")
    lines.append("### 集中度（跨账户同标的合计）")
    if top_symbols:
        for g in top_symbols[:10]:
            h = g["h"]
            pct = (g["mv_cny"] / total_cny * 100) if total_cny else 0.0
            accts = "、".join(sorted(g["accounts"]))
            lines.append(
                f"- {h.name or h.symbol}（{h.market.value}:{h.symbol}）：约 {to_display(g['mv_cny']):,.0f} "
                f"{cur_label}，占 {pct:.1f}%（账户：{accts}）"
            )
    else:
        lines.append("- 无可用集中度数据")

    lines.append("")
    lines.append("## 持仓明细")
    lines.append("| 标的 | 市场 | 代码 | 账户 | 币种 | 数量 | 成本价 | 现价 | 市值 | 未实现盈亏 | 权重(CNY) |")
    lines.append("|------|------|------|------|------|------|-------|------|------|-----------|----------|")
    for r in rows:
        h = r["h"]
        if h.status != HoldingStatus.open:
            continue
        w = (r["mv_cny"] / total_cny * 100) if total_cny else 0.0
        acct = platforms.get(h.platform_id, f"#{h.platform_id}")
        qty = "缺失" if h.quantity is None else f"{h.quantity:g}"
        cpr = "缺失" if h.cost_price is None else f"{h.cost_price:g}"
        cur_p = "缺失" if not _valued(h) else (f"{h.current_price:g}" if h.current_price is not None else "手填")
        mv_native = _fmt(r["mv_native"], h.currency.value, 0) if _valued(h) else "缺失"
        if not _valued(h):
            pnl_native = "未知（缺现价）"
        elif r["pnl"] is None:
            pnl_native = "未知（缺成本）"
        else:
            pnl_native = _fmt(r["pnl"], h.currency.value)
        lines.append(
            f"| {h.name or '—'} | {h.market.value} | {h.symbol or '—'} | {acct} | {h.currency.value} "
            f"| {qty} | {cpr} | {cur_p} | {mv_native} | {pnl_native} | {w:.1f}% |"
        )

    notes = session.exec(
        select(Note).where(
            Note.user_id == user.id,
            Note.note_type.in_(["thesis", "risk", "review", "observation"]),
        ).order_by(Note.updated_at.desc()).limit(20)
    ).all()
    lines.append("")
    lines.append("## 相关投资逻辑与风险笔记")
    if notes:
        for n in notes:
            tag = n.symbol or (n.title or "")[:30]
            body = (n.content or "").strip().replace("\n", " ")
            lines.append(f"- [{n.note_type}] {tag}：{body[:200]}")
    else:
        lines.append("- （无）")

    priced = sum(1 for h in open_holdings if _valued(h))
    lines.append("")
    lines.append("## 数据质量与口径说明")
    lines.append(
        f"- 估值覆盖：{priced}/{len(open_holdings)} 个未清仓持仓有行情或手填金额；"
        "缺失的市值/成本已显式标注「缺失」或「未知」，不代表其值为 0。"
    )
    lines.append("- 现金口径：现金账本主要由入金/出金流水重算，未完整联动证券买卖，故不可视为精确可用余额，也不据此给出精确调仓金额。")
    lines.append("- HKD 通过 7.8 HKD/USD 近似折算，为估算值。")
    lines.append("- 数字由后台统一折算为 CNY 后再换算展示币种，与总览同口径。")

    return "\n".join(lines)
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && .venv-mac-py39/bin/python -m pytest tests/test_portfolio_context.py -v`
Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/portfolio_context.py backend/tests/test_portfolio_context.py
git commit -m "feat(research): add full-account portfolio context builder"
```

---

## Task 4: 组合专用输出章节（prompt builder）

**Files:**
- Modify: `backend/research_prompt_builder.py`
- Test: 扩展 `backend/tests/test_research_tracking.py`

**Interfaces:**
- Consumes: `build_prompt(...)` 现有签名。
- Produces: `build_prompt(..., is_portfolio: bool = False)` —— `is_portfolio=True` 时使用组合专用章节列表（含「账户与配置分析」「持仓建议」表格），否则沿用原「研究闭环输出要求」。

- [ ] **Step 1: 写组合输出章节测试**

Append to `backend/tests/test_research_tracking.py`:

```python
def test_prompt_portfolio_has_account_and_holding_sections():
    import research_prompt_builder
    prompt = research_prompt_builder.build_prompt(
        skill_md="# Skill\nContent",
        target_name="组合",
        report_language="zh",
        is_portfolio=True,
    )
    for keyword in ["账户与配置分析", "持仓建议", "标的", "触发条件", "行动项"]:
        assert keyword in prompt, f"组合 prompt 缺少：{keyword}"


def test_prompt_non_portfolio_keeps_generic_sections():
    import research_prompt_builder
    prompt = research_prompt_builder.build_prompt(
        skill_md="# Skill\nContent",
        target_name="腾讯",
        report_language="zh",
        is_portfolio=False,
    )
    assert "账户与配置分析" not in prompt  # 单公司模板不含组合专用章节
    assert "结论摘要" in prompt
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv-mac-py39/bin/python -m pytest tests/test_research_tracking.py -k portfolio_or_non_portfolio -v`
Expected: FAIL — `TypeError: build_prompt() got an unexpected keyword argument 'is_portfolio'`。

- [ ] **Step 3: 实现组合输出章节**

Modify `backend/research_prompt_builder.py`：
1. 在 `_research_loop_requirements` 之后新增 `_portfolio_loop_requirements`：

```python
def _portfolio_loop_requirements(lang: str) -> str:
    if lang == "en":
        return (
            "## Portfolio Output Requirements\n\n"
            "The report **MUST** include the following sections as Level 2 headings (`##`):\n\n"
            "1. **## Summary** — 3 bullet points on the portfolio's state, key issues, and priority actions.\n"
            "2. **## Account & Allocation Analysis** — accounts, asset types, currency exposure, concentration, cash status.\n"
            "3. **## Holding Recommendations** — a GFM table with columns: "
            "Holding | Account/Cross-account | Weight | Recommendation | Rationale | Trigger or To-Verify.\n"
            "4. **## Core Assumptions** — assumptions and unstated investor preferences.\n"
            "5. **## Key Risks** — risks and their impact paths.\n"
            "6. **## Questions to Verify** — missing data, cash needs, external facts.\n"
            "7. **## Tracking Metrics** — observable metrics and review timing.\n"
            "8. **## Action Items** — bullet list, each starting with `- `.\n"
        )
    return (
        "## 组合输出要求\n\n"
        "报告**必须**包含以下章节，使用二级 Markdown 标题（`##`）：\n\n"
        "1. **## 结论摘要** — 用 3 条要点说明组合现状、主要问题和优先行动。\n"
        "2. **## 账户与配置分析** — 各账户、资产类型、币种分布、集中度和现金状态。\n"
        "3. **## 持仓建议** — 使用表格：`标的 | 账户/跨账户合计 | 当前权重 | 建议 | 依据 | 触发条件或待核实事项`。\n"
        "4. **## 核心假设** — 列出支撑建议的假设和尚未提供的用户偏好。\n"
        "5. **## 主要风险** — 风险及其影响路径，区分已知风险与需验证判断。\n"
        "6. **## 待验证问题** — 会改变结论的缺失数据、资金需求或外部事实。\n"
        "7. **## 跟踪指标** — 与建议对应的可观察指标和复查时机。\n"
        "8. **## 行动项** — 必须使用以 `- ` 开头的清单，每条写明对象、动作、理由和触发条件。\n"
    )
```

2. 修改 `build_prompt` 签名与组装（第 144、209 行附近）：

```python
def build_prompt(
    skill_md: str,
    target_name: str,
    symbol: str = "",
    market: str = "",
    holding_ctx: str = "",
    portfolio_ctx: str = "",
    report_language: str = "zh",
    extra_instruction: str = "",
    is_portfolio: bool = False,
) -> str:
```

将原 `f"{_research_loop_requirements(report_language)}"` 替换为：

```python
f"{_portfolio_loop_requirements(report_language) if is_portfolio else _research_loop_requirements(report_language)}"
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && .venv-mac-py39/bin/python -m pytest tests/test_research_tracking.py -v`
Expected: 全部 PASS（含既有 `test_prompt_contains_research_loop_*`）。

- [ ] **Step 5: Commit**

```bash
git add backend/research_prompt_builder.py backend/tests/test_research_tracking.py
git commit -m "feat(research): add portfolio-specific output sections to prompt builder"
```

---

## Task 5: 接线 display_currency、上下文与摘要端点（后端）

**Files:**
- Modify: `backend/models.py`
- Modify: `backend/research_service.py`
- Modify: `backend/routers/research.py`
- Test: 扩展 `backend/tests/test_research.py`

**Interfaces:**
- Consumes: `build_account_context`（Task 3）、`build_prompt(is_portfolio=...)`（Task 4）。
- Produces: `POST /api/research/runs` 接受 `display_currency`；`GET /api/research/portfolio-summary` 返回最新成功组合报告摘要；`_extract_bullets(md, headings)` 复用。

- [ ] **Step 1: 写摘要提取与接线测试**

Append to `backend/tests/test_research.py`:

```python
def _seed_report(session, user_id, template_key="portfolio-review", status="completed",
                 report_md=None, updated_at=None):
    from models import ResearchReport
    from datetime import datetime
    r = ResearchReport(
        user_id=user_id, template_key=template_key, title="组合复盘", target_name="组合",
        status=status, report_md=report_md, updated_at=updated_at or datetime.utcnow(),
    )
    session.add(r)
    session.commit()
    session.refresh(r)
    return r.id


def test_portfolio_summary_extracts_sections(engine2, user_a):
    from models import ResearchReport
    client = _make_client(engine2, user_a)
    with Session(engine2) as s:
        _seed_report(s, user_a.id, report_md=(
            "## 结论摘要\n- 第一条结论\n- 第二条\n- 第三条\n\n"
            "## 主要风险\n- 集中度风险\n\n## 行动项\n- 减仓 A\n"
        ))
    r = client.get("/api/research/portfolio-summary")
    assert r.status_code == 200
    body = r.json()
    assert body["report"] is not None
    assert body["report"]["conclusions"] == ["第一条结论", "第二条", "第三条"]
    assert body["report"]["risks"] == ["集中度风险"]
    assert body["report"]["actions"] == ["减仓 A"]
    client.app.dependency_overrides.clear()


def test_portfolio_summary_empty_when_no_report(engine2, user_a):
    client = _make_client(engine2, user_a)
    r = client.get("/api/research/portfolio-summary")
    assert r.status_code == 200
    assert r.json()["report"] is None
    client.app.dependency_overrides.clear()


def test_create_run_portfolio_uses_new_context(engine2, user_a):
    from models import Platform, Holding
    client = _make_client(engine2, user_a)
    with Session(engine2) as s:
        p = Platform(user_id=user_a.id, name="P"); s.add(p); s.commit(); s.refresh(p)
        s.add(Holding(user_id=user_a.id, platform_id=p.id, name="茅台", symbol="600519",
                      market="A", quantity=10, current_price=100))
        s.commit()
    with patch("research_service.ALLOW_SYSTEM_AI_FALLBACK", True), \
         patch("ai_client.is_configured", return_value=True), \
         patch("ai_client.start_research", return_value="mock-id-pf"):
        resp = client.post("/api/research/runs", json={
            "template_key": "portfolio-review",
            "display_currency": "USD",
        })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "展示币种：USD" in (data["input_context_md"] or "")
    client.app.dependency_overrides.clear()
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv-mac-py39/bin/python -m pytest tests/test_research.py -k portfolio_summary_or_display -v`
Expected: FAIL — `GET /api/research/portfolio-summary` 404；`display_currency` 被忽略。

- [ ] **Step 3: models.py 扩展请求 schema**

Modify `backend/models.py` 的 `ResearchRunCreate`，在 `use_web_search` 之后加：

```python
    display_currency: Currency = Currency.CNY
```

- [ ] **Step 4: research_service.create_run 接线**

Modify `backend/research_service.py`：
1. 顶部 import 增加：`import portfolio_context`。
2. `create_run` 签名在 `use_web_search: bool` 之后加参数 `display_currency: Currency = Currency.CNY`。
3. 替换第 234–243 行的上下文构建段为：

```python
    # 5. Build context
    is_portfolio = template_key == "portfolio-review"
    input_context_md = ""
    if is_portfolio:
        input_context_md = portfolio_context.build_account_context(session, user, display_currency)
    elif holding:
        input_context_md = _holding_context(holding, session)
```

4. 第 253–262 行 `build_prompt(...)` 调用末尾加 `is_portfolio=is_portfolio`。

- [ ] **Step 5: routers/research.py 接线 + 摘要端点**

Modify `backend/routers/research.py`：
1. `create_run`（136–162 行）在 `use_web_search=data.use_web_search,` 之后加 `display_currency=data.display_currency,`。
2. 将 `_extract_action_items`（306–325 行）泛化并新增 `_extract_bullets`（替换现有实现）：

```python
def _extract_bullets(md: str, headings: tuple) -> List[str]:
    """提取给定标题（如「行动项」「主要风险」）下的清单条目。"""
    heading_re = re.compile(
        r'^#{1,3}\s+(' + "|".join(re.escape(x) for x in headings) + r')\s*$',
        re.IGNORECASE,
    )
    next_heading_re = re.compile(r'^#{1,3}\s+')
    list_re = re.compile(r'^\s*(?:[-*+]|\d+\.)\s+(.+)')
    in_section = False
    out: List[str] = []
    for line in md.splitlines():
        s = line.strip()
        if heading_re.match(s):
            in_section = True
            continue
        if in_section:
            if next_heading_re.match(s) and not heading_re.match(s):
                break
            m = list_re.match(line)
            if m:
                out.append(m.group(1).strip())
    return out


def _extract_action_items(report_md: str) -> List[str]:
    return _extract_bullets(report_md, ("行动项", "Action Items"))
```

3. 新增端点（放在 `list_reports` 之后）：

```python
@router.get("/portfolio-summary")
def portfolio_summary(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """返回最新成功组合报告的派生摘要，供首页总览卡片使用。"""
    reports = session.exec(
        select(ResearchReport).where(
            ResearchReport.user_id == user.id,
            ResearchReport.template_key == "portfolio-review",
            ResearchReport.status == "completed",
        ).order_by(ResearchReport.updated_at.desc()).limit(20)
    ).all()
    report = next((r for r in reports if r.report_md), None)
    if not report:
        return {"report": None}
    conclusions = _extract_bullets(report.report_md, ("结论摘要", "Summary"))
    risks = _extract_bullets(report.report_md, ("主要风险", "Key Risks"))
    actions = _extract_bullets(report.report_md, ("行动项", "Action Items"))
    return {
        "report": {
            "id": report.id,
            "title": report.title,
            "as_of": (report.completed_at or report.created_at).isoformat(),
            "status": report.status,
            "conclusions": conclusions[:3],
            "risks": risks[:5],
            "actions": actions[:5],
            "degraded": not conclusions,
        }
    }
```

- [ ] **Step 6: 运行确认通过**

Run: `cd backend && .venv-mac-py39/bin/python -m pytest tests/test_research.py tests/test_research_tracking.py -v`
Expected: 全部 PASS（既有 `test_extract_action_items_*` 仍通过，因 `_extract_bullets` 兼容原行为）。

- [ ] **Step 7: Commit**

```bash
git add backend/models.py backend/research_service.py backend/routers/research.py backend/tests/test_research.py
git commit -m "feat(research): wire display_currency + portfolio summary endpoint"
```

---

## Task 6: Research 页预选、偏好与报告深链（前端）

**Files:**
- Modify: `frontend/src/pages/Research.jsx`

**Interfaces:**
- Consumes: `POST /api/research/runs`（含 `display_currency`，Task 5）；`useDisplaySettings()`。
- Produces: 支持 `/research?preset=portfolio-review&report_id=<id>`；组合分析可选偏好（投资目标/持有周期/风险偏好/近期资金需求）并入 `extra_instruction`；run 载荷带 `display_currency`。

- [ ] **Step 1: 导入与读取路由参数**

Modify `frontend/src/pages/Research.jsx`：
1. 加 `import { useSearchParams } from 'react-router-dom'`（已有 `useNavigate`）。
2. 加 `import { useDisplaySettings } from '../displaySettings.jsx'`。
3. 组件内（`const navigate = useNavigate()` 之后）加：

```jsx
const [searchParams] = useSearchParams()
const { displayCurrency } = useDisplaySettings()
```

- [ ] **Step 2: 预选组合分析与报告深链**

在模板列表加载完成的 `useEffect`（260–264 行）内，加载后处理预选与深链。替换为：

```jsx
useEffect(() => {
  listResearchTemplates().then((ts) => {
    setTemplates(ts)
    if (searchParams.get('preset') === 'portfolio-review') {
      const tpl = ts.find((t) => t.key === 'portfolio-review')
      if (tpl) handleSelectTemplate(tpl)
    }
  }).catch(() => {})
  listHoldings().then(setHoldings).catch(() => {})
  listResearchReports().then((rs) => {
    setReports(rs)
    const rid = searchParams.get('report_id')
    if (rid) {
      const target = rs.find((r) => String(r.id) === rid)
      if (target) setViewReport(target)
    }
  }).catch(() => {})
}, []) // eslint-disable-line react-hooks/exhaustive-deps
```

- [ ] **Step 3: 组合分析可选偏好字段**

在 `{isPortfolioReview && (<Form.Item name="report_language" ...>)}`（568–572 行）之后，加偏好输入（仍用 `extra_instruction` 承载）：

```jsx
{isPortfolioReview && (
  <Row gutter={8}>
    <Col xs={24} sm={12}>
      <Form.Item name="investment_goal" label="投资目标（可选）" style={{ marginBottom: 8 }}>
        <Input placeholder="如：长期增值 / 退休储备" />
      </Form.Item>
    </Col>
    <Col xs={24} sm={12}>
      <Form.Item name="holding_period" label="持有周期（可选）" style={{ marginBottom: 8 }}>
        <Input placeholder="如：3–5 年" />
      </Form.Item>
    </Col>
    <Col xs={24} sm={12}>
      <Form.Item name="risk_preference" label="风险偏好（可选）" style={{ marginBottom: 8 }}>
        <Input placeholder="如：稳健 / 激进" />
      </Form.Item>
    </Col>
    <Col xs={24} sm={12}>
      <Form.Item name="cash_needs" label="近期资金需求（可选）" style={{ marginBottom: 8 }}>
        <Input placeholder="如：半年内需用 5 万" />
      </Form.Item>
    </Col>
  </Row>
)}
```

- [ ] **Step 4: 组装偏好到 extra_instruction 并传 display_currency**

替换 `handleLaunch` 中构建 `payload` 的段落（307–318 行）为：

```jsx
const investorParts = [
  values.investment_goal ? `投资目标：${values.investment_goal}` : '投资目标：未知',
  values.holding_period ? `持有周期：${values.holding_period}` : '持有周期：未知',
  values.risk_preference ? `风险偏好：${values.risk_preference}` : '风险偏好：未知',
  values.cash_needs ? `近期资金需求：${values.cash_needs}` : '近期资金需求：未知',
].join('；')
const extra = [values.extra_instruction, isPortfolioReview ? `【投资者背景】${investorParts}` : '']
  .filter(Boolean).join('\n')
const payload = {
  template_key: selectedTemplate.key,
  target_name: values.target_name || null,
  symbol: values.symbol || null,
  market: values.market || null,
  related_holding_id: values.related_holding_id ? Number(values.related_holding_id) : null,
  report_language: values.report_language || 'zh',
  ai_provider: values.ai_provider || 'deepseek',
  ai_model: values.ai_model || MODEL_OPTIONS[values.ai_provider || 'deepseek']?.[0]?.value,
  extra_instruction: extra || null,
  use_web_search: values.use_web_search !== false,
  display_currency: displayCurrency,
}
```

- [ ] **Step 5: 构建验证**

Run: `cd frontend && npm run build`
Expected: 构建成功。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Research.jsx
git commit -m "feat(research): preset portfolio-review, investor prefs, report deep-link"
```

---

## Task 7: 首页「AI 分析全部账户」入口与总览摘要卡片（前端）

**Files:**
- Modify: `frontend/src/pages/Dashboard.jsx`

**Interfaces:**
- Consumes: `GET /api/research/portfolio-summary`（Task 5）。
- Produces: 首页 CTA 按钮「AI 分析全部账户」→ `/research?preset=portfolio-review`；总览摘要卡片（数据时点 + 3 结论 + 风险 + 行动 + 查看/重新分析入口）；隐私模式收起摘要正文。

- [ ] **Step 1: 补导入并加 CTA 按钮**

先在 `frontend/src/pages/Dashboard.jsx` 补导入（供本任务与摘要卡片使用）：antd 导入行加 `Collapse`，图标导入行加 `RobotOutlined`。

然后在 Dashboard CTA `Space`（204–233 行）内，`AI 投研` 按钮之后加：

```jsx
<Button
  type="primary"
  icon={<RobotOutlined />}
  onClick={() => navigate(`/research?preset=portfolio-review&currency=${displayCurrency}`)}
>
  AI 分析全部账户
</Button>
```

- [ ] **Step 2: 总览摘要卡片**

在「总资产走势」Card 之前插入摘要卡片：

```jsx
{portfolioSummary && portfolioSummary.report && (
  <Card
    size="small"
    title={<Space><RobotOutlined style={{ color: '#1677ff' }} />全账户 AI 分析</Space>}
    extra={
      <Space size={8}>
        <Button size="small" onClick={() => navigate(`/research?report_id=${portfolioSummary.report.id}`)}>
          查看完整报告
        </Button>
        <Button size="small" type="primary" onClick={() => navigate('/research?preset=portfolio-review')}>
          重新分析
        </Button>
      </Space>
    }
  >
    <Text type="secondary" style={{ fontSize: 12 }}>
      数据时点：{(portfolioSummary.report.as_of || '').slice(0, 16).replace('T', ' ')}
    </Text>
    {portfolioSummary.report.degraded ? (
      <div style={{ marginTop: 8, fontSize: 13, color: '#8c8c8c' }}>
        摘要无法可靠提取，请点击「查看完整报告」。
      </div>
    ) : (
      <Collapse
        ghost
        size="small"
        defaultActiveKey={masked ? [] : ['summary']}
        items={[
          {
            key: 'summary',
            label: '核心结论',
            children: (
              <>
                <ul style={{ margin: 0, paddingLeft: 20 }}>
                  {portfolioSummary.report.conclusions.map((c, i) => (
                    <li key={i} style={{ fontSize: 13 }}>{c}</li>
                  ))}
                </ul>
                {portfolioSummary.report.risks?.length > 0 && (
                  <div style={{ marginTop: 6, fontSize: 13, color: '#595959' }}>
                    主要风险：{portfolioSummary.report.risks.join('；')}
                  </div>
                )}
                {portfolioSummary.report.actions?.length > 0 && (
                  <div style={{ marginTop: 6, fontSize: 13, color: '#595959' }}>
                    优先行动：{portfolioSummary.report.actions.join('；')}
                  </div>
                )}
              </>
            ),
          },
        ]}
      />
    )}
  </Card>
)}
```

（`masked` 已存在，来自 `isMasked()`；隐私模式下 `defaultActiveKey=[]` 即默认收起可能含金额的摘要正文。）

- [ ] **Step 3: 构建验证**

Run: `cd frontend && npm run build`
Expected: 构建成功。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Dashboard.jsx
git commit -m "feat(dashboard): all-account AI analysis entry + summary card"
```

---

## Task 8: 回归验证与文档

**Files:**
- Modify: `ARCHITECTURE.md`（或 `docs/superpowers/plans/` 说明）—— 记录新端点 `GET /api/snapshots?range=`、`GET /api/research/portfolio-summary` 与「全账户分析」流程。

**Interfaces:** 无新增。

- [ ] **Step 1: 全量后端回归**

Run: `cd backend && .venv-mac-py39/bin/python -m pytest -q`
Expected: 全部通过（重点确认既有 `test_research.py`、`test_research_tracking.py`、`test_summary_extended.py`、`test_position.py` 不回归）。

- [ ] **Step 2: 前端构建**

Run: `cd frontend && npm run build`
Expected: 构建成功。

- [ ] **Step 3: 浏览器交互核查**

Run: `python dev.py`（起前后端，浏览器自动打开）。逐项核查：

1. 曲线右上角 6 档选择器，默认「半年」，切换即时刷新曲线且不触发 AI 请求。
2. 「最大」显示全部历史；月末/闰年/7 天边界与后端 `_range_start` 一致。
3. 空区间显示「暂无净值记录」；单点显示单点与日期；历史不足显示实际日期范围。
4. 币种切换：曲线范围保持不变，历史金额用快照保存值（不按当前汇率重算）。
5. 快速连续切换范围无错乱（过时请求被忽略）。
6. 首页「AI 分析全部账户」→ 进入预选 portfolio-review 的投研页，可填偏好、确认模型、手动生成。
7. 生成完成后首页出现摘要卡片（数据时点 + 3 结论 + 风险 + 行动 + 查看/重新分析）。
8. 行动项可保存为投资笔记，重复保存不重复生成。
9. 隐私模式下摘要正文默认收起。
10. 未配置 Key / 失败 / 重试状态明确；单公司投研流程不受影响。

- [ ] **Step 4: 文档更新**

在 `ARCHITECTURE.md` 的 API/研究章节补一行说明（如无对应章节则追加「接口变更」小节）：

```markdown
- `GET /api/snapshots` 新增可选 `range`（max/1y/6m/3m/1m/1w），旧 `days` 保留；两者同传时 `range` 优先。
- `GET /api/research/portfolio-summary` 返回最新成功组合报告的派生摘要（结论/风险/行动）。
- `POST /api/research/runs` 新增可选 `display_currency`，用于 portfolio-review 的展示币种。
```

- [ ] **Step 5: Commit**

```bash
git add ARCHITECTURE.md
git commit -m "docs: document snapshot range and all-account analysis endpoints"
```

---

## Self-Review Notes

- **Spec coverage:** 需求 A（全账户 AI 分析）覆盖：总览摘要（Task 7）、完整报告（复用现有投研页，Task 6）、行动项（复用 `generate_tracking_notes`，Task 5 回归确认）、展示币种与偏好（Task 5/6）、跨账户合并/清仓收益/缺失标注/HKD 与现金口径（Task 3）、组合专用章节（Task 4）。需求 B（走势范围）覆盖：6 档选择器、默认半年、记忆、`range` 参数与日历边界、旧 `days` 兼容、独立加载/过时忽略、空/单点/历史不足、币种保留范围（Task 1/2）。验收方式：Pytest（mock AI）+ 前端构建 + 浏览器交互（Task 8）。
- **未新增业务表**：展示币种通过 `input_context_md` 文本保存，符合「先评估已有字段」约束。
- **Type consistency:** `display_currency` 全链路为 `Currency` 枚举（`ResearchRunCreate.display_currency: Currency` → router 透传 → `research_service.create_run(display_currency: Currency)` → `build_account_context(display_currency: Currency)`）。`build_prompt(is_portfolio: bool)` 与 Task 5 调用一致。`_range_start(range_key, today)` 返回 `Optional[str]`，Task 1 测试按此断言。
- **Legacy 保留:** `routers/research.py` 的 `/prompts` 旧接口与其本地 `_portfolio_context`、`research_service._portfolio_context` 保持不变，其既有测试（`test_prompt_portfolio_review`、`test_research_service_portfolio_context_uses_fx_rates` 等）继续通过；新流程走 `portfolio_context.build_account_context`。
