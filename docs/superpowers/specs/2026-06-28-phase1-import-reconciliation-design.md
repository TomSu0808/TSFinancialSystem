# Phase 1: 导入与对账系统 — 设计规格

## 目标

降低用户冷启动成本，使 TSFinancialSystem 从"手动维护工具"升级为"可对账的资产账本"。实现一个可扩展的券商导入与对账系统，优先支持富途 CSV、IBKR Activity Statement、通用字段映射器、导入 preview 校验、导入后对账页面、异常交易修正入口和现金账本。

## 约束

不要实现真实券商 API OAuth，不要引入 Alembic，不要重构 models.py，不要改变现有手动交易路径。

---

## 1. 架构概览

```
backend/
├─ importers/              # 券商 CSV 解析器
│  ├─ __init__.py
│  ├─ base.py              # BaseImporter + ImportedTransactionDraft
│  ├─ futu.py              # 富途 CSV 解析
│  ├─ ibkr.py              # IBKR Activity Statement 解析
│  └─ generic.py           # 通用字段映射导入
├─ import_service.py       # 导入编排层：preview / commit / 去重
├─ reconciliation_service.py  # 对账服务
├─ routers/
│  └─ imports.py           # 导入 + 对账 API
├─ models.py               # 新增 ImportSession, ReconSnapshot
```

## 2. 数据模型（新增）

### ImportSession
- id, user_id, platform_id, broker_type (futu/ibkr/generic)
- file_name, detected_fields (JSON), user_mapping (JSON)
- rows_json (解析后所有行), summary_json (计数)
- status: previewed / committed / failed
- created_at

### ReconSnapshot
- id, user_id, import_session_id (FK→ImportSession)
- platform_id, symbol, name, currency
- broker_quantity, system_quantity, quantity_diff
- broker_cost, system_cost, cost_diff
- status: matched / warning / error
- created_at

## 3. 新增 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/imports/preview | 上传 → 解析 → 存 ImportSession → 返回预览 |
| POST | /api/imports/{id}/commit | 确认导入 → 写 Transaction → 触发持仓重算 |
| GET | /api/imports/{id}/reconciliation | 返回对账结果 |
| GET | /api/imports | 列出历史导入会话 |
| GET | /api/imports/{id} | 单次导入详情 |

## 4. 数据流

```
上传文件 → BaseImporter.parse() → [ImportedTransactionDraft]
    → detect_fields(header) → 自动识别列名
    → user_confirm_mapping() → 字段映射确认
    → validate() → 逐行校验 (date/action/currency/quantity/price/amount + 超卖检测)
    → dedup_check() → 行 hash 去重
    → ImportSession (status=previewed) → 存库
    → 用户确认 → commit:
        逐行写 Transaction.create()
        → _sync_txn_holding() → 绑定 derived 持仓
        → recompute_holding() → 重算
        → ReconSnapshot.compute() → 对账快照
```

## 5. 现金账本

deposit/withdraw → _update_cash_holding():
- 每个 (platform_id, currency) 自动维护 source=derived, asset_type=cash 的 Holding
- deposit: manual_value += amount
- withdraw: manual_value -= amount（不允许为负）
- 读取: return cash_holding.manual_value

## 6. 前端改动

1. Transactions 页面「导入 CSV」按钮 → 「导入交易」打开 Drawer
2. 步骤：选择券商类型 → 上传文件 → 字段自动识别 → 确认/修改映射 → preview 表格 → 确认导入
3. 对账：导入结果区嵌入对账视图（Collapse 可展开）
4. error 行红底、warning 行黄底、duplicate 行灰底

## 7. 测试

后端 12+ 测试：
1. 富途 CSV 解析成功
2. 富途 CSV 字段缺失报错
3. IBKR CSV 解析成功
4. 通用字段映射成功
5. preview 不写入 Transaction
6. commit 写入 Transaction 并触发持仓重算
7. 重复导入去重
8. preview 发现超卖
9. 对账 matched / warning / error
10. deposit / withdraw 影响现金余额
11. 多用户隔离

---

## 开发约束

1. 不要做真实券商 API OAuth
2. 不要接入富途 OpenD
3. 不要接入 IBKR Client Portal Gateway
4. 不要做自动交易
5. 不要引入大型任务队列
6. 不要重构整个 models.py
7. 不要引入 Alembic
8. 不要破坏现有手动交易录入
9. 不要改变现有用户数据隔离逻辑
10. 金额计算复用项目已有 Decimal / valuation 逻辑