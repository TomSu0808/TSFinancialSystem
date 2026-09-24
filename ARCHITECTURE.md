# 工程结构总览 (ARCHITECTURE)

> 本文件给「快速读懂整个项目」用。每次大改后请同步更新对应小节。
> 配套文件：迭代记录见 [CHANGELOG.md](CHANGELOG.md)，使用说明见 [README.md](README.md)。

---

## 1. 一句话定位

个人资产管理平台：按**平台**（富途/盈透等）+ **币种**（CNY/USD/HKD）管理多类资产（股票/基金/债券/加密/现金），
展示总资产、今日涨跌、未实现/已实现盈亏；**买入/卖出流水自动驱动持仓数量与移动加权成本**。

**技术栈**：FastAPI + SQLite(SQLModel) + akshare（后端） / React + Vite + Ant Design（前端），前后端分离。

---

## 2. 目录结构（忽略 .venv / node_modules / dist / __pycache__）

```
FinancialSystem/
├─ start.bat / start.sh / stop.bat / stop.sh   一键启停（后端:8000 + 前端:5173）
├─ dev.py                 跨平台 dev 脚手架（start / stop / setup / reset-password / list-users）
├─ README.md              使用与部署说明
├─ CHANGELOG.md           迭代日志
├─ ARCHITECTURE.md        本文件
├─ Dockerfile             多阶段构建（Node → Python）；前端产物由 FastAPI 同源托管
├─ fly.toml               Fly.io 部署配置 + 持久卷挂载
│
├─ backend/                       FastAPI 后端
│  ├─ main.py                     入口：初始化 DB + 挂载路由 + CORS + 托管前端静态文件
│  ├─ database.py                 SQLite 引擎 / init_db（自动迁移补列）/ get_session
│  ├─ models.py                   ★核心：表模型 + API schema + 市值/涨亏/盈亏计算口径
│  ├─ position.py                 ★交易驱动核心：replay_transactions / recompute_holding / resolve_derived_holding
│  ├─ price_provider.py           行情抓取（akshare / CoinGecko）
│  ├─ fx_provider.py              汇率抓取（open.er-api.com，回退中行）
│  ├─ auth.py                     JWT token 签发/校验，get_current_user 依赖项
│  ├─ config.py                   从 .env 读取配置（SECRET_KEY / CORS / 注册开关等）
│  ├─ manage.py                   CLI 工具（python manage.py reset-password / list-users）
│  ├─ requirements.txt            依赖（FastAPI / SQLModel / akshare / python-jose / bcrypt …）
│  ├─ data.db                     SQLite 数据库文件（运行时生成）
│  └─ routers/
│     ├─ auth.py                  /api/auth   注册 · 登录 · 获取当前用户 · 改密码
│     ├─ platforms.py             /api/platforms   平台 CRUD
│     ├─ holdings.py              /api/holdings    持仓 CRUD + 刷新行情；derived 持仓只读保护
│     ├─ transactions.py          /api/transactions  流水 CRUD；买/卖/分红自动绑定并重算 derived 持仓
│     ├─ summary.py               /api/summary     总资产/涨跌/未实现盈亏/已实现盈亏/总收益；每日快照 upsert
│     ├─ fx.py                    /api/fx          汇率查询/刷新
│     ├─ snapshots.py             /api/snapshots   历史净值曲线数据
│     ├─ notes.py                 /api/notes       投资心得 CRUD
│     └─ backup.py                /api/backup      整账 JSON 导出/导入（往返保真）
│
├─ backend/tests/                 Pytest 测试
│  ├─ conftest.py                 内存 DB + 覆盖 get_session/get_current_user 夹具
│  ├─ test_position.py            replay_transactions 纯逻辑单测
│  └─ test_transactions_drive_holdings.py  通过 API 端到端验证交易驱动持仓
│
└─ frontend/                      React 前端
   ├─ vite.config.js              /api 代理到 :8000，开 host 供手机访问
   ├─ index.html
   └─ src/
      ├─ main.jsx                 入口（挂载 Router）
      ├─ App.jsx                  布局 + 路由 + 用户菜单（隐私/深色/改密码/备份）
      ├─ api/index.js             ★前端唯一 API 层（axios + JWT 拦截器，全部接口在此）
      ├─ constants.js             枚举/常量/隐私打码 fmt
      ├─ holdings.js              derived/manual 持仓展示辅助函数（复用于多个页面）
      └─ pages/
         ├─ Login.jsx             登录 / 注册
         ├─ Dashboard.jsx         总览：总资产、今日涨跌、总收益（悬浮拆分）、走势折线图、配置饼图
         ├─ Platforms.jsx         平台列表 + 展开行（持仓、市值、占比）
         ├─ PlatformDetail.jsx    某平台下的持仓管理（新建/编辑/删除，derived 只读）
         ├─ Transactions.jsx      交易流水账本（买/卖/分红/入金/出金/其它；保存后自动同步持仓）
         └─ Notes.jsx             投资心得备忘
```

---

## 3. 数据模型（backend/models.py，最该先读的文件）

六张表：

| 表 | 作用 | 关键字段 |
|---|---|---|
| `User` | 登录账号 | id, username, email, password_hash, created_at |
| `Platform` | 资产所在平台 | id, user_id(FK), name, note |
| `Holding` | 一条持仓 | platform_id(FK), user_id(FK), currency, asset_type, market, symbol, name, quantity, manual_value, cost_price, current_price, prev_close, price_updated_at; `source`(manual/derived), `status`(open/closed), `realized_pnl`, `realized_income` |
| `Transaction` | 交易流水 | user_id(FK), platform_id(FK), `holding_id`(FK→Holding，系统自动绑定), date, action(buy/sell/dividend/deposit/withdraw/other), name, symbol, currency, quantity, price, fee, amount, note |
| `FxRate` | 汇率（pair=USDCNY）| rate, updated_at |
| `Snapshot` | 每人每天一条净值快照 | user_id(FK), day(YYYY-MM-DD), total_cny, total_usd, ts |
| `Note` | 投资心得 | user_id(FK), title, content, created_at, updated_at |

**枚举**：`Currency`(CNY/USD/HKD) · `AssetType`(stock/etf/fund/bond/crypto/cash) · `Market`(A/HK/US/FUND/CRYPTO/NONE) · `HoldingSource`(manual/derived) · `HoldingStatus`(open/closed) · `TxnAction`(buy/sell/dividend/deposit/withdraw/other)

**四个计算口径函数（改动需谨慎，前后端都依赖其语义）**：
- `market_value(h)`：`manual_value` 优先，否则 `quantity × current_price`，都没有记 0。
- `day_change(h)`：今日涨跌额 = `quantity × (current_price − prev_close)`；手填金额或缺昨收记 0。
- `cost_basis(h)`：`quantity × cost_price`；缺任一返回 None。
- `profit(h)`：`market_value − cost_basis`；成本未知返回 None。

> 抓不到价的资产（现金/债券）用 `manual_value` 手填市值，`market=NONE`。

---

## 4. 交易驱动持仓机制（backend/position.py）

**核心设计**：`source=derived` 的持仓由交易流水唯一决定，不允许直接修改数量/成本。

| 函数 | 职责 |
|---|---|
| `replay_transactions(txns)` | 纯函数：按 (date, id) 升序重放流水，返回 `PositionState`（quantity / avg_cost / realized_pnl / realized_income / realized_pnl_incomplete）；无副作用，便于单测 |
| `recompute_holding(session, holding_id)` | 带 DB 副作用：从 DB 读流水 → replay → 回写持仓（quantity/cost_price/realized_pnl/realized_income/status）|
| `resolve_derived_holding(session, user, platform_id, symbol, currency, ...)` | 按 (user, platform, symbol, currency) 查 derived 持仓；`create_if_missing=True` 时自动新建 |
| `resolve_position(session, user, txn)` | 按 (user, platform, symbol, currency) 匹配唯一持仓；同标的重复持仓报错，不猜测合并 |
| `prepare_position(session, user, txn)` | 交易入库前，命中手填持仓时保存期初 `adjust` 记录并转 `derived` |
| `opening_transaction(holding, date)` | 把手填数量/成本固化为一条 `adjust` 期初记录（无现金流）|

**持仓状态**：买入可自动建仓（`create_if_missing`）；卖出/分红只绑定已存在的 derived 持仓；清仓（quantity ≈ 0）自动置 `status=closed`，默认在持仓列表隐藏。

**持仓校准（`adjust` 流水，2026-09-24）**：`adjust` 的 `quantity` 表示校准后的**绝对数量**、`price` 为平均成本（可空），不产生现金流、不计已实现收益。手填持仓（`source=manual`）首次买卖时，`prepare_position` 自动先写入一条交易前的期初 `adjust` 记录并把该持仓转为 `derived`，从而支持「无买入流水也能卖出」。校准当天重放重设数量与成本基准，不把差额当作收益；成本未知（`price=None`）的卖出置 `realized_pnl_incomplete=True`，补齐原校准成本后重算。同一平台、代码、币种存在多个持仓时拒绝操作，要求先整理重复持仓。

**绑定时机**：每次创建/修改/删除交易时，`_sync_txn_holding()` 自动判断新旧 holding_id、触发受影响持仓的重算。

---

## 5. API 一览（前缀均为 /api，文档 http://localhost:8000/docs）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/health | 健康检查 |
| POST | /api/auth/register | 注册 |
| POST | /api/auth/login | 登录，返回 JWT token |
| GET | /api/auth/me | 当前登录用户信息 |
| POST | /api/auth/change-password | 改密码（校验原密码）|
| GET/POST | /api/platforms | 列出 / 新建平台 |
| PUT/DELETE | /api/platforms/{id} | 改 / 删平台 |
| GET | /api/holdings | 列出（`platform_id` / `currency` / `include_closed` 过滤）|
| POST | /api/holdings | 新建持仓（manual 专用；derived 持仓由交易自动建）|
| PUT | /api/holdings/{id} | 改持仓（derived 持仓禁止改 quantity/cost_price/symbol/currency/platform_id）|
| DELETE | /api/holdings/{id} | 删持仓（derived 持仓需先删流水）|
| POST | /api/holdings/refresh-prices | ★刷新全部行情，写回价格并存 Snapshot |
| GET | /api/transactions | 列出（`platform_id` 过滤，按日期倒序）|
| POST | /api/transactions | 新建流水/校准；buy 自动建/绑 derived 持仓，adjust 重设绝对数量与平均成本，均触发重算 |
| PUT | /api/transactions/{id} | 改流水；旧/新 derived 持仓均重算 |
| DELETE | /api/transactions/{id} | 删流水；相关 derived 持仓重算 |
| GET | /api/fx/rate | 当前汇率 |
| POST | /api/fx/refresh | 刷新汇率 |
| GET | /api/summary?currency= | 总资产/今日涨跌/未实现盈亏/已实现盈亏/总收益；触发每日快照 upsert |
| GET | /api/snapshots | 历史净值快照（绘曲线用）|
| GET/POST | /api/notes | 列出 / 新建心得 |
| PUT/DELETE | /api/notes/{id} | 改 / 删心得 |
| GET | /api/backup/export | 导出整账 JSON |
| POST | /api/backup/import | 导入（覆盖式，清空再重建）|

### 接口变更（全账户 AI 分析 / 走势时间范围）

- `GET /api/snapshots` 新增可选 `range`（max/1y/6m/3m/1m/1w），旧 `days` 保留；两者同传时 `range` 优先。
- `GET /api/research/portfolio-summary` 返回最新成功组合报告的派生摘要（结论/风险/行动）。
- `POST /api/research/runs` 新增可选 `display_currency`，用于 portfolio-review 的展示币种。

---

## 6. 关键数据流

1. **手填资产**：`PlatformDetail.jsx` → `POST /api/holdings` → 落 `Holding`(source=manual)。
2. **买入驱动建仓**：`Transactions.jsx` → `POST /api/transactions`(action=buy) → `_sync_txn_holding` → `resolve_derived_holding(create_if_missing=True)` 建/找 derived 持仓 → `recompute_holding` 重算数量与成本。
3. **卖出结转盈亏**：同上，sell → replay 计算已实现盈亏，回写 `realized_pnl`，数量归零时置 `status=closed`。
4. **持仓校准 / 无买入卖出**：手填持仓直接记卖出或「持仓校准」→ `prepare_position` 写期初 `adjust` 记录并转 `derived` → `replay_transactions` 按 (date,id) 重放，扣减数量、重设成本基准；成本未知卖出标 `realized_pnl_incomplete`。
5. **刷新行情**：Dashboard 点「更新行情」→ `POST /api/holdings/refresh-prices` → `price_provider` 按 market/symbol 抓价 → 写回 `current_price`/`prev_close`。
6. **看总览**：`GET /api/summary?currency=CNY|USD` → 后端用 `market_value`/`day_change`/`cost_basis` 累加 + 已实现盈亏 + `FxRate` 换算 → 顺带 upsert 每日快照。
7. **币种切换**：前端只换 `currency` 参数重拉 summary，金额由后端换算。

---

## 7. 改动指南（给后续迭代的「最小修改路径」提示）

- **加一种资产类型/市场** → 改 `models.py` 枚举 + `price_provider.py` 抓价分支 + 前端 `constants.js` 文案。
- **改市值/涨亏算法** → 只动 `models.py` 的 `market_value`/`day_change`，前后端都复用，勿在别处重算。
- **改持仓派生逻辑** → 只动 `position.py` 的 `replay_transactions`（注意 `adjust` 校准流水的回放顺序、绝对数量语义与成本缺失标志 `realized_pnl_incomplete`），测试在 `tests/test_position.py` 与 `tests/test_holding_calibration.py`。
- **加接口** → 在对应 `routers/*.py` 加路由，并在前端 `api/index.js` 同步加函数。
- **改数据库结构** → 改 `models.py` 后在 `database.py` 的 `init_db` 里加 `addColumn`（SQLite 不支持自动迁移）；开发期也可删 `backend/data.db` 重建。
- **上云**：SQLite→PostgreSQL 改 `DATABASE_URL` 环境变量；APScheduler 定时刷新；券商 API 直连（见 README Roadmap）。

---

## 8. 启动备忘

- 一键：`python dev.py start`（或双击 `start.bat`/`start.sh`）。停止：`dev.py stop`。
- 后端单独：`backend/` 下 `.\.venv\Scripts\python.exe -m uvicorn main:app --reload`
- 前端单独：`frontend/` 下 `npm run dev`
- 测试：`backend/` 下 `.\.venv\Scripts\pytest tests/ -v`
- Windows 注意：用 PowerShell 直接调 `.\.venv\Scripts\python.exe`，勿在 Git Bash 跑 Store 版 Python。


## 每日盈亏与登录刷新（2026-09-12）

`dailypnl` 独立保存每日累计收益基准和原币种日差额，不从资产总额差推断盈亏。
`GET /api/snapshots/daily-pnl` 返回当前用户的日盈亏；`POST /api/automation/run-now?reason=login` 记录登录自动刷新。
全量定时任务同时保存资产快照和日盈亏，Fly 配置保留一个常驻实例。启动自动创建新表并给旧 `automationrun` 补充 `user_id`。
备份 v2 增加日盈亏与资产快照，兼容旧格式；恢复后重建日收益基准。

组合摘要的 `as_of` 来自保存的输入数据时点，`latest_task` 独立于旧成功报告。新报告采用固定八节排版契约。
使用方法、计算限制、发布配置及验收说明见 [每日盈亏与组合分析](docs/daily-pnl-and-portfolio-analysis.md)。
