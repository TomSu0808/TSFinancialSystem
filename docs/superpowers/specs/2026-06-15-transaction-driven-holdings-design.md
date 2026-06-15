# 交易驱动持仓 · Transaction-Driven Holdings — 设计文档 (PRD)

> 日期：2026-06-15 ｜ 状态：已评审通过，待实现
> 配套：[ARCHITECTURE.md](../../../ARCHITECTURE.md) · [CHANGELOG.md](../../../CHANGELOG.md)

---

## 1. 背景与问题

当前 `Transaction`（交易流水）与 `Holding`（持仓）是**两本独立的账**：

- 交易流水代码注释明确"**不自动改持仓**"，且 `Transaction` 没有指向具体 `Holding` 的外键，仅靠 `symbol` 松散关联。
- 用户买入一笔，需在「交易记录」记一遍，再到「持仓」手动改数量和成本 → **双重录入、必然对不上账**。
- `Holding.cost_price` 是**单一手填字段**：多次加仓不算移动平均、部分卖出不结转、已实现盈亏无处归集 → **盈亏数字不准**。

盈亏与净资产是本产品区别于券商 App 的核心价值，数字不可信则信任崩塌。

## 2. 目标 (v1)

让"交易驱动型"持仓的**数量**与**成本**由交易流水**自动派生**，交易成为唯一事实来源；
分清**未实现盈亏 / 已实现盈亏 / 分红收入**。

**成功标准：**
- 录入买入/卖出流水后，对应持仓的数量、移动加权成本**自动更新**，无需手改。
- 部分/全部卖出能正确结转**已实现盈亏**；清仓后持仓留底，收益不丢。
- 存量手填持仓**行为与数字完全不变**（零风险迁移）。

## 3. 非目标 (明确推迟到 v2+)

- 公司行为：拆股/合股、送股、红利再投 —— v1 不自动处理（用户可临时用手填型或手动调整）。
- FIFO/批次(lot) 成本法与税务报表口径 —— v1 仅移动加权平均。
- 分红抵减成本 —— v1 分红只计为已实现收益，不动成本。
- 行情抓取逻辑 —— 完全不改，`current_price` 仍由现有"刷新行情"写入。

## 4. 已评审决策

| # | 决策 | 选择 |
|---|---|---|
| 1 | 存量持仓如何共存 | **混合模式**：derived（交易驱动）与 manual（手填）并存；老数据默认 manual |
| 2 | 成本法 | **移动加权平均**（手续费摊入成本） |
| 3 | v1 范围 | 买入/卖出**驱动持仓**；分红/入金/出金**仅记录**；公司行为推迟 |
| 4 | 清仓处理 | **保留为 `closed` 记录**，主列表默认隐藏，已实现盈亏留底 |

## 5. 数据模型改动

### 5.1 `Holding` 新增字段

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `source` | enum `manual` / `derived` | `manual` | 持仓类型；老数据无痛兼容 |
| `status` | enum `open` / `closed` | `open` | 清仓后置 `closed`，主列表默认隐藏 |
| `realized_pnl` | float | `0.0` | 累计已实现盈亏（卖出时累加） |
| `realized_income` | float | `0.0` | 累计分红/利息（仅记录类） |

- 对 `derived` 持仓：`quantity`、`cost_price` 为**派生结果**（重算后写回，UI 只读）。
- 对 `manual` 持仓：所有字段行为**不变**。

### 5.2 `Transaction` 新增字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `holding_id` | FK→holding（可空） | 显式关联到具体持仓，取代 symbol 松散关联；旧流水留空兼容 |

### 5.3 派生持仓的身份

**身份键 = `(platform_id, symbol, currency)`**。同一标的在不同平台视为两个独立持仓。
录入买入交易时，系统按此键查找/自动创建对应 `derived` 持仓并回填 `holding_id`。

### 5.4 计算口径（`models.py`）

- `cost_basis(h)`：derived 用 `quantity × cost_price`(派生均价)；manual 不变。
- `profit(h)` → **未实现盈亏** = `market_value − cost_basis`（逻辑不变）。
- 新增**总收益** = 未实现盈亏 + `realized_pnl` + `realized_income`。

## 6. 核心派生算法

**模块：** 新建 `backend/position.py`，导出 `recompute_holding(session, holding_id)`。
**触发：** 关联到某 derived 持仓的交易被增/删/改时，对该持仓**全量重算**。

> **为何全量重算**：个人账本单持仓交易量小（几条~几十条），全量重放简单、无累积误差、
> 编辑/删除历史交易也能自愈。增量更新在改旧交易时易错，不值得。

**重放逻辑**（该持仓所有交易按 `date` 升序）：

```
状态：qty=0, avg_cost=0, realized_pnl=0, realized_income=0

buy(q, price, fee):
    新成本 = qty*avg_cost + q*price + fee
    qty   += q
    avg_cost = 新成本 / qty                       # 移动加权平均，手续费摊入

sell(q, price, fee):
    realized_pnl += q*price - q*avg_cost - fee    # 已实现盈亏，手续费抵减
    qty   -= q
    # avg_cost 不变；qty 归 0 时 avg_cost 归 0

dividend(amount):
    realized_income += amount                     # 不动 qty / avg_cost

deposit / withdraw / other:
    跳过
```

**回写 Holding：** `quantity=qty`、`cost_price=avg_cost`、`realized_pnl`、`realized_income`；
`status = closed if abs(qty) < 1e-9 else open`。

**异常：** 卖出多于持仓（qty 变负）→ 不阻止录入，持仓打 ⚠️"数量异常，请检查流水"标记
（个人记账常漏录买入，提示比硬拦更友好）。

## 7. API 改动

### 7.1 `routers/transactions.py`
- `POST` / `PUT` / `DELETE`：操作后**自动触发对应持仓重算**。
- 创建买入时若身份键无 derived 持仓 → **自动创建**并回填 `holding_id`。
- 改动涉及两个持仓（改了 symbol/platform）→ **两边都重算**。

### 7.2 `routers/holdings.py`
- `GET /api/holdings`：返回加 `source`/`status`/`realized_pnl`/`realized_income`；默认仅 `open`，
  `?include_closed=true` 返回清仓记录。
- `POST`：`source` 由前端传。
- `PUT`：对 `derived` 持仓**拒绝手改 `quantity`/`cost_price`**（400，提示"请改流水"）；其余字段可改。

### 7.3 `routers/summary.py`
- 收益拆分：`unrealized_pnl`、`realized_pnl`、`realized_income`、`total_return`。
- 排除 `closed` 持仓市值（qty=0 自然为 0），但**计入其 `realized_pnl`**。

## 8. 前端 / UX 改动

- **新建资产**（`PlatformDetail.jsx`）：顶部切换「按交易记录(derived)」/「直接手填(manual)」。
  - derived → 表单为"录第一笔买入"，提交后自动建持仓 + 首笔流水。
  - manual → 维持现有手填表单（现金/债券走此路）。
- **持仓列表**（`PlatformDetail.jsx` / `Platforms.jsx`）：
  - derived 的数量/成本只读 + 🔗"由流水计算"标识；点击可查关联流水。
  - 新增「已实现盈亏」列；清仓持仓默认折叠在底部"已清仓"分区；卖超 ⚠️ 标记。
- **总览**（`Dashboard.jsx`）：收益拆为 未实现 / 已实现 / 分红收入 / 总收益（一个总数 + 悬浮明细，避免过载）。
- **交易记录**（`Transactions.jsx`）：录买卖可选关联"平台 + 标的"(holding_id)；保存后提示"已更新 XX 持仓：数量 100→150"（功能的 aha 时刻）。
- **API 层**（`api/index.js`）：同步 `include_closed`、收益拆分字段、derived 只读处理。

## 9. 迁移与兼容（零风险）

- `init_db()` 加幂等迁移（沿用 `_migrate_add_user_id` 写法）：给 `holding` 补 4 列、`transaction` 补 `holding_id`。
- 老持仓默认 `source=manual, status=open` → **行为与数字完全不变**。
- 老流水 `holding_id` 留空，不受影响。
- **"转为交易驱动"**（可选、不强制）：用当前 `quantity`/`cost_price` 生成一条期初建仓交易，
  之后该持仓变 derived —— 混合模式按需迁移的落地方式。
- `routers/backup.py` 导出/导入加新字段；导入旧备份缺字段给默认值，不报错。

## 10. 测试（TDD，先写测试）

**`position.py` 纯函数单测（重点）：**
- 多笔加仓 → 移动加权均价正确（¥10×100 + ¥20×100 → 均价 15）。
- 部分卖出 → 已实现盈亏正确、均价不变。
- 全部卖出 → `status=closed`、qty=0、`realized_pnl` 累计正确。
- 手续费摊入（买入加、卖出减）。
- 卖超 → 标记异常、不崩溃。
- 删除/修改中间一笔交易 → 全量重算自愈。

**接口层：** 加交易后 GET 持仓数量/成本已变；derived 持仓 PUT 改数量被 400 拦截。
**回归：** manual 持仓行为、总览汇总、备份导入导出往返。

## 11. 影响文件清单

- 后端：`models.py`、`database.py`、新增 `position.py`、`routers/transactions.py`、
  `routers/holdings.py`、`routers/summary.py`、`routers/backup.py`
- 前端：`PlatformDetail.jsx`、`Platforms.jsx`、`Dashboard.jsx`、`Transactions.jsx`、
  `api/index.js`、`constants.js`
- 文档：`ARCHITECTURE.md`、`CHANGELOG.md`
