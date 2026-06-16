# 工程结构总览 (ARCHITECTURE)

> 本文件给「快速读懂整个项目」用。每次大改后请同步更新对应小节。
> 配套文件：迭代记录见 [CHANGELOG.md](CHANGELOG.md)，使用说明见 [README.md](README.md)。

---

## 1. 一句话定位

个人资产管理平台：按**平台**（富途/盈透等）+ **币种**（CNY/USD）管理多类资产（股票/基金/债券/加密/现金），
展示总资产、今日涨跌，支持实时汇率与 ¥/$ 切换、一键刷新行情。

**技术栈**：FastAPI + SQLite(SQLModel) + akshare（后端） / React + Vite + Ant Design（前端），前后端分离。

---

## 2. 目录结构（只列关键文件，忽略 .venv / node_modules / dist / __pycache__）

```
FinancialSystem/
├─ start.bat / start.sh / stop.bat / stop.sh   一键启停（后端:8000 + 前端:5173）
├─ README.md          使用与部署说明
├─ CHANGELOG.md       迭代日志
├─ ARCHITECTURE.md    本文件
│
├─ backend/                       FastAPI 后端
│  ├─ main.py                     入口：初始化 DB + 挂载路由 + CORS
│  ├─ database.py                 SQLite 引擎 / init_db / get_session
│  ├─ models.py                   ★核心：表模型 + API schema + 市值/涨跌计算口径
│  ├─ price_provider.py           行情抓取（akshare / CoinGecko）
│  ├─ fx_provider.py              汇率抓取（open.er-api.com，回退中行）
│  ├─ position.py                 持仓派生计算（交易流水 → 数量/移动加权成本/已实现盈亏；replay_transactions / recompute_holding / resolve_derived_holding）
│  ├─ requirements.txt            依赖
│  ├─ data.db                     SQLite 数据库文件（运行时生成）
│  └─ routers/
│     ├─ platforms.py             /api/platforms   平台 CRUD
│     ├─ holdings.py              /api/holdings    持仓 CRUD + 刷新行情
│     ├─ fx.py                    /api/fx          汇率查询/刷新
│     └─ summary.py               /api/summary     总资产/涨跌汇总
│
└─ frontend/                      React 前端
   ├─ vite.config.js              /api 代理到 :8000，开 host 供手机访问
   ├─ index.html
   └─ src/
      ├─ main.jsx                 入口（挂载 Router）
      ├─ App.jsx                  布局 + 路由（总览 / 平台管理 / 平台详情）
      ├─ api/index.js             ★前端唯一 API 层（axios，全部接口在此）
      ├─ constants.js             枚举/常量（资产类型、市场、币种等显示文案）
      └─ pages/
         ├─ Dashboard.jsx         总览：总资产、今日涨跌、币种切换、刷新
         ├─ Platforms.jsx         平台列表 + 增删改
         └─ PlatformDetail.jsx    某平台下的持仓管理
```

---

## 3. 数据模型（backend/models.py，最该先读的文件）

四张表：

| 表 | 作用 | 关键字段 |
|---|---|---|
| `Platform` | 资产所在平台 | id, name, note |
| `Holding`  | 一条持仓 | platform_id(FK), currency, asset_type, market, symbol, name, quantity, manual_value, cost_price, current_price, prev_close, price_updated_at; **新增**：`source`(manual/derived), `status`(open/closed), `realized_pnl`(已实现盈亏), `realized_income`(已实现收益/分红) |
| `Transaction` | 交易流水 | platform_id(FK), date, action(buy/sell/dividend/deposit/withdraw/other), name, symbol, currency, quantity, price, fee, amount, note; **新增**：`holding_id`(FK → Holding，derived 持仓绑定) |
| `FxRate`   | 汇率（单行，pair=USDCNY） | rate, updated_at |
| `Snapshot` | 每次刷新埋点（为画历史曲线预留） | ts, total_cny, total_usd |

**枚举**：`Currency`(CNY/USD/HKD) · `AssetType`(stock/etf/fund/bond/crypto/cash) · `Market`(A/HK/US/FUND/CRYPTO/NONE) · `HoldingSource`(manual/derived) · `HoldingStatus`(open/closed)

**两个核心计算口径函数（改动需谨慎，前后端都依赖其语义）**：
- `market_value(h)`：手填金额 `manual_value` 优先，否则 `quantity × current_price`，都没有记 0。
- `day_change(h)`：今日涨跌额 = `quantity × (current_price − prev_close)`；手填金额或缺昨收记 0。

> 抓不到价的资产（现金/债券）用 `manual_value` 手填市值，`market=NONE`。

---

## 4. API 一览（前缀均为 /api，文档 http://localhost:8000/docs）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/health | 健康检查 |
| GET/POST | /api/platforms | 列出 / 新建平台 |
| PUT/DELETE | /api/platforms/{id} | 改 / 删平台 |
| GET/POST | /api/holdings | 列出（可按 platform 过滤）/ 新建持仓 |
| PUT/DELETE | /api/holdings/{id} | 改 / 删持仓 |
| POST | /api/holdings/refresh-prices | ★刷新全部行情，写回价格并存 Snapshot |
| GET | /api/fx/rate | 当前汇率 |
| POST | /api/fx/refresh | 刷新汇率 |
| GET | /api/summary?currency= | 总资产/今日涨跌汇总（按币种换算） |

---

## 5. 关键数据流

1. **新增资产**：前端 `pages/PlatformDetail.jsx` → `api/index.js` → `POST /api/holdings` → 落 `Holding` 表。
2. **刷新行情**：Dashboard 点「更新行情」→ `POST /api/holdings/refresh-prices` → `price_provider` 按 `market`/`symbol` 抓价 → 写回 `current_price`/`prev_close` → 计算并存 `Snapshot`。
3. **看总览**：Dashboard → `GET /api/summary?currency=CNY|USD` → 后端用 `market_value`/`day_change` 累加，按 `FxRate` 换算到目标币种。
4. **币种切换**：前端只换 `currency` 参数重新拉 summary，金额由后端换算。

---

## 6. 改动指南（给后续迭代的「最小修改路径」提示）

- **加一种资产类型/市场** → 改 `models.py` 枚举 + `price_provider.py` 抓价分支 + 前端 `constants.js` 文案。
- **改市值/涨亏算法** → 只动 `models.py` 的 `market_value`/`day_change`，前后端都复用，勿在别处重算。
- **加接口** → 在对应 `routers/*.py` 加路由，并在前端 `api/index.js` 同步加函数（前端只通过这一层调后端）。
- **改数据库结构** → 改 `models.py` 后注意 SQLite 不自动迁移；开发期可删 `backend/data.db` 重建，或后续引入迁移工具。
- **上云预留**：SQLite→PostgreSQL、加 APScheduler 定时刷新、加 JWT 多用户、券商 API 直连（见 README 第四节）。

---

## 7. 启动备忘

- 一键：双击 `start.bat`（Win）/ `./start.sh`。停止：`stop.bat` / `stop.sh`。
- 后端单独：`backend/` 下 `.\.venv\Scripts\python.exe -m uvicorn main:app --reload`
- 前端单独：`frontend/` 下 `npm run dev`
- Windows 注意：用 PowerShell 直接调 `.\.venv\Scripts\python.exe`，勿在 Git Bash 跑 Store 版 Python 虚拟环境。
