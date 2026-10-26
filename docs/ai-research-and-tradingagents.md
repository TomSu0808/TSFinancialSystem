# AI 投研 v2 与 TradingAgents 接入

本文说明 2026-10 的 AI 投研升级：任务入口、结构化摘要、报告追问、研究更新、跟踪事项，以及在“投资委员会讨论”中接入固定版本 TradingAgents。

## 边界

- 系统只做资产记录、研究和复盘。
- 研究流程不会新增、修改或删除持仓、现金、交易记录。
- 研究评级不会自动转成 Transaction。
- TradingAgents Worker 只接收权限校验后的数据快照，不导入资产数据库，不挂载数据库路径，也没有下单/撤单/转账工具。
- 取消会终止 Worker 子进程；是否真正中断取决于进程终止结果，界面会如实显示。

## 交互与数据流

### 1. 任务入口与默认模板

投研首页提供四个入口，仍保留“全部研究工具”：

| 入口 | 默认模板 |
|---|---|
| 研究一家公司 | `investment-research` |
| 分析最新财报 | `earnings-review` |
| 检查我的持仓 | `portfolio-review` |
| 复查投资逻辑 | `thesis-tracker` |

从持仓详情进入时会带上 `holding_id`，前端自动选择持仓并填入名称、代码、市场。后端仍会校验代码/市场是否与持仓一致；同名、同代码或跨市场歧义会返回 400，要求用户选择具体持仓。

### 2. 输入预览

`POST /api/research/preview` 与正式提交共用同一套标的解析和上下文构建，但不调用模型、不写数据库。返回：

- 研究对象、市场、代码、币种、数据时点。
- 是否携带持仓、成本、现金、历史研究、笔记。
- 缺失行情/成本及多币种提示。
- 本次标准和多 Agent 执行方式。
- 实际组合上下文预览（由后端计算，前端不重算）。

`include_holding_context=false` 时不携带个人持仓；组合复盘必须携带。

### 3. 结构化摘要

标准研究在同一次模型回答末尾要求输出 `research-json` 代码块。系统解析后存入 `ResearchReport.report_json`，并从正文中移除该代码块。解析失败时：

- 保留完整 Markdown；
- `report_json.degraded=true`；
- 界面降级展示原文，不补造摘要字段。

事实、分析判断、待验证假设分别用 `kind: fact / analysis / assumption` 标记。`fact` 没有来源时界面显示“来源缺失”。来源一律不标记“已核验”。

### 4. 报告追问

- 数据表：`researchmessage`，每条消息独立保存，关联报告和用户。
- 一个报告一条连续对话；不覆盖原报告。
- 首次提问自动携带原报告和 `input_snapshot_json`。
- 默认不联网；用户可开启“补充联网核查”。只有真正返回的来源才标为新增来源，并记录获取时间。
- 历史过长时保留最早 2 条与最近 6 条，并标记“已压缩”；完整消息仍在数据库中。
- 失败保留用户问题；取消按钮会记录 Provider 是否确认中断及可能仍计费的风险。

### 5. 更新研究

`POST /api/research/reports/{id}/update` 以旧报告为基线创建新版本：

- 新报告 `parent_report_id` 指向旧报告，`version` 递增。
- 标准研究把旧报告正文放入基线上下文，并要求模型列出新增事实、假设支持/推翻、结论变化、未解决事项、资料缺口。
- 多 Agent 引擎不接收旧报告原文，因此多 Agent 更新使用结构化字段的确定性差异，并在 `changes.comparison_method=deterministic` 明确标注，不自动声称假设被支持或推翻。
- 没有获得可核验新来源时，`changes.coverage_gaps` 明确说明，不能把历史资料包装成最新数据。

### 6. 跟踪事项

复用 `Note`/决策日志，不新建第二套跟踪表。新增字段：

- `metric` 观察指标；
- `review_date` 复查日期；
- `trigger_condition` 事件/指标条件；
- `report_version` 来源研究版本。

流程改为：提取候选 → 用户勾选/编辑 → 保存。没有明确日期时不会编造日期；“下一次财报后”保存为事件条件。重复保存返回已有记录，不重复生成。

## TradingAgents 接入

### 引擎与版本

- 上游：`https://github.com/TauricResearch/TradingAgents`
- 固定提交：`e8f5503e9b86d5c2710b0c76b1f686703968c9df`
- 固定版本：`0.7.0`
- 依赖文件：`backend/requirements-tradingagents.txt`

TradingAgents 要求 Python 3.11+ 和 pandas 3，而后端仍使用 pandas 2。因此 Docker 中把它安装到独立 venv：

```
/opt/tradingagents-venv
TRADINGAGENTS_PYTHON=/opt/tradingagents-venv/bin/python
```

构建时可用 `--build-arg INSTALL_TRADINGAGENTS=0` 跳过；此时多 Agent 会明确提示引擎不可用，标准研究不受影响。

### 执行方式

- 只在 `investment-team`（投资委员会讨论）中提供“标准讨论 / 多 Agent 协作”。
- 多 Agent 使用独立 Worker 子进程；每个任务一个进程组。
- 默认分析师：基本面、行情、机构新闻；`social` 关闭。
- 多空讨论与风险讨论各 1 轮。
- 策略节点只输出研究观点和情景；界面明确标注“非交易指令”。
- 保存各阶段报告、最终结论、模型配置、数据快照、引擎版本/提交、用量与工具调用次数。
- 用户记忆、缓存、检查点、结果目录均在 `TRADINGAGENTS_DATA_ROOT/users/{user_id}` 下隔离。
- Provider Key 只注入当前 Worker 子进程环境；不改写共享进程 `os.environ`，并清除其他 Provider Key 避免回退串用。

### 多币种与不支持资产

TradingAgents 的组合输入只支持单一币种。适配层：

- 只携带与分析标的同币种的持仓和现金；
- 不把其他币种按汇率混入平均成本；
- 在输入快照和界面明确列出被排除的持仓；
- 基金、债券、现金等不支持的资产类型在提交前拒绝，并提示改用标准研究。

### 代码映射

- US：原代码。
- HK：补足 4 位并加 `.HK`。
- A 股：6/9 开头 → `.SS`；0/3 开头 → `.SZ`。
- Crypto：无后缀时加 `-USD`。
- 其他市场/资产：拒绝。

## 进度、用量、预算与取消

- 标准研究与多 Agent 都在后台执行：提交立即返回（最多等待 0.6 秒以吸收极快响应），前端轮询真实事件与状态，不需要手动刷新。
- 进度只来自 `researchrunevent` 真实事件（标准 Provider 状态、Worker 阶段、工具调用）；前端不生成虚假百分比。
- `usage_json` 保存提供商原始 usage 归一化结果；缓存读取单独记录，不重复加到普通输入。
- 费用仅在 `AI_PRICE_TABLE_JSON` 有对应模型价格且 usage 完整时计算；否则显示未知原因。
- 默认限制：标准 12 次调用、多 Agent 60 次；输出 token 120000；标准 1800 秒、多 Agent 3600 秒。可用环境变量覆盖。
- Worker 在回调中检查调用次数、输出 token、时间；父进程另有超时终止。达到预算后停止后续步骤。
- 取消标准 Provider 时记录 Provider 是否确认；取消 Worker 时终止进程组。
- 同一用户提交有互斥锁；相同 `idempotency_key` 或相同提示/配置在 10 分钟内返回已有任务，避免重复付费。

## 数据库迁移

启动时 `database.init_db()` 自动：

- 新增 `researchrunevent`、`researchmessage`、`researchpreference` 表；
- 为 `researchreport` 补版本、结构化摘要、快照、用量、预算、来源状态等列；
- 为 `note` 补跟踪事项字段。

迁移是幂等的，不清空已有数据。旧报告字段为空，前端按原 Markdown 展示。回滚代码不会删除新增列/表；如需彻底回滚，请先备份 `data.db`，再恢复旧版本代码和备份。

SQLite 生产库建议升级前导出备份：

```
GET /api/backup
```

当前备份格式已包含新增报告字段；追问消息属于独立对话数据，建议同时保留数据库文件或做整库备份。

## API 摘要

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/research/preview` | 输入预览，不调用模型 |
| GET/PUT | `/api/research/preferences` | 研究偏好 |
| POST | `/api/research/runs` | 新建研究；支持 `execution_mode`、`include_holding_context`、`idempotency_key` |
| GET | `/api/research/reports/{id}/events` | 真实任务事件 |
| POST | `/api/research/reports/{id}/update` | 生成新版本 |
| GET | `/api/research/reports/{id}/versions` | 版本链 |
| GET/POST | `/api/research/reports/{id}/messages` | 追问历史 / 发起追问 |
| POST | `/api/research/reports/{id}/messages/{mid}/cancel` | 停止追问 |
| GET | `/api/research/reports/{id}/tracking-candidates` | 跟踪事项预览 |
| POST | `/api/research/reports/{id}/tracking-notes` | 保存用户选择的事项 |

## 测试与验证边界

自动化测试使用 mock/fake Provider 和 fake TradingAgents 上游包，不产生模型费用：

- `backend/tests/test_research_v2.py` 覆盖预览、歧义、结构化降级、追问、版本、跟踪、隔离、资产不变、Worker 子进程路径、取消。
- fake 上游包执行的是真实 `tradingagents_worker.py` 子进程和适配层，不是静态模拟返回值；但没有调用真实的 TradingAgents 行情/新闻供应商，也没有验证线上模型。
- 前端 `frontend/tests/research-helpers.test.js` 覆盖结构化解析与来源合并。

未验证的外部能力：真实 TradingAgents 行情/新闻数据源、真实 Provider 的联网检索与费用、真实用户 Key 的多 Agent 长任务。上线前应使用测试账号和独立预算做一次小规模实测。
