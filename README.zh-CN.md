# TSFinancialSystem

<div align="center">

**一个可自部署的多币种个人资产管理与 AI 投研平台。**

[English](README.md) | [在线体验](https://tsfinancialsystem.fly.dev/) | [架构说明](ARCHITECTURE.md) | [技术路线图](TECHNICAL_ROADMAP.md) | [更新日志](CHANGELOG.md)

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.128-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-5-646CFF?logo=vite&logoColor=white)](https://vitejs.dev/)
[![Ant Design](https://img.shields.io/badge/Ant%20Design-5-0170FE?logo=antdesign&logoColor=white)](https://ant.design/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)](Dockerfile)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

## 项目定位

TSFinancialSystem 面向个人投资者，用来在一个私有 Web 应用中管理股票、基金、债券、加密货币和现金资产。系统按平台账户、资产类型和币种组织数据，支持交易流水驱动持仓、行情与汇率刷新、资产配置分析、净值曲线、CSV 导入与对账、投资决策日志，以及 AI 辅助投研报告。

它是一个个人投资管理工作台：把资产、交易、复盘和 AI 投研放在同一个流程里。

## 适合谁

- 有多个券商、银行账户、钱包或基金账户的个人投资者。
- 同时持有 CNY、USD、HKD 等多币种资产的人。
- 希望用交易流水自动还原持仓、成本和已实现盈亏的人。
- 希望把 AI 投研报告、行动项和复盘记录长期沉淀下来的人。
- 想自部署并掌控个人资产数据的人。

## 在线体验

访问：<https://tsfinancialsystem.fly.dev/>

线上版本支持注册、登录、多用户数据隔离和 HTTPS。请不要在公开演示环境中录入真实敏感资产信息。

## 核心能力

| 能力 | 说明 |
| --- | --- |
| 多平台资产管理 | 按券商、银行、钱包或自定义账户管理资产，例如富途、盈透、老虎、银行卡、加密钱包。 |
| 多币种资产总览 | 支持 CNY、USD、HKD 等币种；总览、账户列表和账户详情都可切换人民币 / 美元，并记住展示偏好。 |
| 交易驱动持仓 | 买入、卖出、分红等交易流水自动更新 derived 持仓、移动加权成本、已实现盈亏和清仓状态。 |
| Dashboard 总览 | 查看总资产、今日涨跌、总收益、未实现 / 已实现盈亏、资产配置、净值曲线和数据状态；每日盈亏按逐仓位昨日基准记录，新增或缺价持仓不会拖垮其他持仓。 |
| 行情与汇率刷新 | 支持 A 股、港股、美股、基金、加密货币和 USD/CNY 汇率刷新；新增、修改、删除或导入交易后自动更新行情。 |
| CSV 导入与对账 | 支持富途、IBKR、通用 CSV 导入流程；导入前预览校验，导入后生成对账结果。 |
| 现金账本 | 按「平台 + 币种」管理现金；卖出净额自动留在账户中，提现/出金单独扣减现金，支持现金校准、流水查询和透支校验。 |
| 手机端操作 | 五栏底部导航，持仓、现金和交易卡片，展开详情、交易分页、折叠筛选及竖向录入表单。 |
| 投资决策日志 | 用结构化笔记记录买入逻辑、风险、复盘、行动项和观察事项，并关联标的或持仓。 |
| AI 投研工作台 | 四种任务入口（研究公司 / 财报 / 持仓 / 投资逻辑），保留全部 AI Berkshire 模板；提交前预览实际携带的数据，支持 GPT、DeepSeek、GLM、Claude 等 Provider。 |
| 结构化报告与追问 | 报告顶部固定结构化摘要（结论、事实与来源、风险、影响、下一步），事实/分析/假设分开标注；可在报告内追问，回答独立保存、不覆盖原报告。 |
| 研究与跟踪闭环 | 支持「更新这份研究」生成新版本并保留版本链；从报告中预览、勾选并保存跟踪事项到决策日志，没有明确日期时不编造日期。 |
| 多 Agent 协作 | 投资委员会模板可调用固定版本 TradingAgents：独立 Worker 子进程、默认关闭 social、多空/风险各一轮、无资产写接口；用户缓存与记忆按账号隔离。 |
| 隐私与安全 | 支持 JWT 鉴权、多用户数据隔离、金额打码、深色模式、邮箱验证、找回密码和 BYOK。 |
| 自部署 | 一个 Docker 镜像同时托管 React 前端和 FastAPI 后端，默认 SQLite，也可通过 `DATABASE_URL` 使用 PostgreSQL。 |

## 典型使用流程

1. 注册账号并创建平台，例如券商、银行、钱包或自定义账户。
2. 添加手动持仓，或录入买入、卖出、分红、入金、出金、现金校准等交易流水。
3. 需要批量迁移时，通过 CSV 导入历史交易，并查看预览校验和对账结果。
4. 保存交易后行情自动更新；需要刷新汇率或重试行情时，可使用总览的更新按钮。
5. 在 Dashboard 查看总资产、收益、资产配置、净值曲线和数据状态。
6. 在 AI 投研页按任务生成研究报告；提交前展开「查看本次研究输入」确认携带的数据。
7. 阅读顶部结构化摘要，必要时在报告内追问，或点击「更新这份研究」核查新资料。
8. 预览并勾选跟踪事项，保存到投资决策日志持续跟踪。
9. 需要迁移或备份时，导出完整账户 JSON。

## 页面概览

| 页面 | 用途 |
| --- | --- |
| Dashboard | 总资产、今日涨跌、收益拆分、资产配置、净值曲线、数据状态和自动刷新入口。 |
| 平台管理 | 按券商、银行或钱包组织资产，并查看每个平台下的持仓。 |
| 持仓详情 | 管理手动资产，查看交易生成的 derived 持仓、成本、盈亏、研究摘要，以及按币种管理的现金账户。 |
| 交易流水 | 记录、筛选、搜索买入 / 卖出 / 分红 / 入金 / 出金 / 现金校准；买卖表单显示当前持仓与现金变动，并执行 CSV 批量导入。 |
| AI 投研 | 按任务入口研究公司/财报/持仓/投资逻辑；输入预览、结构化摘要、报告追问、版本更新与跟踪事项。投委会模板可选 TradingAgents 多 Agent 协作。 |
| 决策日志 | 记录投资逻辑、风险、复盘和行动项，并关联标的、持仓和 AI 报告。 |

## 卖出、现金与提现

账户总资产由持仓市值和现金等资产组成。卖出净额（成交额减手续费，或填写的实际到账金额）自动进入同账户、同币种的现金，可用于下一次买入；资金实际转出账户时才记录「提现/出金」。例如卖出成交额为 1,000 美元、手续费 5 美元，现金增加 995 美元；随后提现 300 美元，现金减少 300 美元。

首笔卖出会自动建立现金记录，无需先初始化。已有但未录入的闲置现金，可在账户详情使用「初始化/校准」，填写该日期的实际现金绝对余额。现金开始追踪前的历史买入不推测入金来源；开始追踪后的买入会扣减现金。校准会覆盖此前累计余额，避免把实际余额重复加到账户中。

交易修改、撤销及导入会重算持仓和现金。行情获取失败时，交易仍保留，页面提示继续显示上次价格。升级会重建历史卖出现金；历史缺少入金形成的缺口可以补录或校准，但新增、扩大的透支会被拒绝。

## 手机端

手机底部可直接切换总览、账户、交易、投研和笔记。持仓、现金流水和交易以卡片展示，展开后查看成本、手续费、备注或操作；交易筛选默认收起，列表每页 20 条，录入表单竖向排列。币种切换只影响展示，保留原始交易币种。

价格/仓位提醒功能已于 2026-10-09 移除，包括页面、接口及自动评估任务；行情与汇率的定时刷新继续运行。

## 数据来源

| 数据类型 | 来源 | 说明 |
| --- | --- | --- |
| A 股、港股、美股、场内基金 | akshare / 东方财富快照 | 免费数据源，可能延迟或不完整。 |
| 场外基金 | akshare 基金净值 | 按基金代码获取最新净值。 |
| 加密货币 | CoinGecko Free API | 支持常见 symbol 和 CoinGecko ID。 |
| USD/CNY 汇率 | open.er-api.com，失败时回退到中国银行数据 | 用于 CNY / USD 展示口径换算。 |
| AI 报告 | 用户配置的 AI Provider | 支持用户自带 API Key，不构成投资建议。 |

## AI 投研 v2 与 TradingAgents

投研页以任务为入口，全部 AI Berkshire 模板仍保留在「全部研究工具」：

- **研究一家公司**（单公司深度研究）、**分析最新财报**（财报解读）、**检查我的持仓**（组合复盘）、**复查投资逻辑**（投资论文追踪）。
- 从持仓详情可直接进入研究，自动带入标的；同名、同代码或跨市场歧义时要求选择持仓，系统不猜测。
- 提交前可展开查看本次实际携带的持仓、成本、现金、历史研究、笔记和数据时点；可以关闭「携带个人持仓信息」。
- 报告顶部固定展示核心结论、关键事实与来源、主要风险和反证、对持仓/目标的影响、下一步观察事项；事实、分析判断、待验证假设分别标记，来源不会标记为「已核验」。
- 报告内可追问；首次提问自动携带原报告和输入快照，回答独立保存、不覆盖原报告。默认不联网，开启补充检索后会在回答中注明新增来源与时间。
- 「更新这份研究」以旧报告为基线生成新版本，保留 `parent_report_id` 和版本链；没有新资料时明确说明，不会只改日期。
- 跟踪事项复用投资决策日志：先预览候选，用户勾选/编辑后再保存；支持观察指标、复查日期和事件条件。
- 标准研究与多 Agent 都在后台执行：提交后立即返回，前端轮询真实事件，不需要手动刷新。

**投资委员会多 Agent**：仅在 `investment-team` 模板中提供「多 Agent 协作」，实际调用固定提交的 [TradingAgents](https://github.com/TauricResearch/TradingAgents)（`e8f5503e9b86d5c2710b0c76b1f686703968c9df`）。默认分析师为基本面、行情、机构新闻（关闭 social），多空讨论和风险讨论各一轮，策略节点只输出研究观点和情景。Worker 在独立子进程中运行，不连接资产数据库，用户记忆、缓存、检查点按账号隔离。

**成本与预算**：用量按 Provider 原始 usage 记录，缓存 token 不重复计数；费用只有在配置了 `AI_PRICE_TABLE_JSON` 且用量完整时才计算，否则显示未知。可限制单任务调用次数、输出 token、执行时间和费用；超限停止后续步骤，取消会终止 Worker 或调用 Provider 取消。

详细配置、数据库迁移、API、回滚和验证边界见 [docs/ai-research-and-tradingagents.md](docs/ai-research-and-tradingagents.md)。

## 快速开始

环境要求：

- Python 3.10+
- Node.js 18+

```bash
git clone https://github.com/TomSu0808/TSFinancialSystem.git
cd TSFinancialSystem
python dev.py start
```

`python dev.py start` 会自动补齐本地环境、启动后端 FastAPI 和前端 Vite。

| 服务 | 地址 |
| --- | --- |
| 前端 | <http://localhost:5173> |
| 后端 API | <http://localhost:8000> |
| API 文档 | <http://localhost:8000/docs> |

停止开发服务：

```bash
python dev.py stop
```

只安装环境、不启动服务：

```bash
python dev.py setup
```

## 配置说明

本地开发可复制 `backend/.env.example` 为 `backend/.env`。生产环境请使用平台 secret 管理敏感配置。

| 配置项 | 说明 |
| --- | --- |
| `SECRET_KEY` | JWT 签名密钥，生产环境必须设置为稳定随机值。 |
| `ENV` | 设置为 `production` 时启用生产配置检查。 |
| `DATA_DIR` | SQLite 数据目录，例如 Fly.io 上的 `/data`。 |
| `DATABASE_URL` | 可选数据库连接串；设置后使用 PostgreSQL，否则默认 SQLite。 |
| `ALLOW_REGISTRATION` | 是否允许公开注册，默认 `true`。 |
| `APP_BASE_URL` | 生产环境中用于邮箱验证和找回密码链接的公开地址。 |
| `APP_ENCRYPTION_KEY` | 生产环境必填，用于加密用户 AI API Key。 |
| `ALLOW_SYSTEM_AI_FALLBACK` | 是否允许用户未配置 Key 时回退到系统级 AI Key，默认 `false`。 |
| `AI_PROVIDER` | 默认 AI Provider，可选 `gpt`、`deepseek`、`glm`、`claude`。 |
| `EMAIL_ENABLED` | 是否启用 SMTP 邮件；未启用时验证链接会输出到日志。 |
| `AUTO_REFRESH_ENABLED` | 是否启用定时刷新。 |
| `AUTO_REFRESH_TIME` | 每日刷新时间，格式 `HH:MM`。 |
| `AUTO_REFRESH_TIMEZONE` | 自动刷新使用的时区，默认 `Asia/Shanghai`。 |
| `RESEARCH_MAX_LLM_CALLS` | 单个研究的模型调用上限；默认标准 12、多 Agent 60。 |
| `RESEARCH_MAX_OUTPUT_TOKENS` | 单个研究的输出 token 上限，默认 120000。 |
| `RESEARCH_MAX_SECONDS` | 单个研究的执行时间上限；默认标准 1800、多 Agent 3600 秒。 |
| `RESEARCH_MAX_BUDGET` | 可选单任务费用上限；设置时必须同时配置价格表，否则拒绝启动。 |
| `AI_PRICE_TABLE_JSON` | 各 Provider/模型的每百万 token 单价；未配置时费用显示未知。 |
| `TRADINGAGENTS_PYTHON` | 安装了 TradingAgents 的独立 Python（3.11+）；Docker 默认 `/opt/tradingagents-venv/bin/python`。 |
| `TRADINGAGENTS_DATA_ROOT` | 多 Agent 用户记忆、缓存、检查点和结果的隔离目录；默认 `/data/tradingagents`。 |
| `TRADINGAGENTS_MAX_TOOL_ROUNDS` | 单个分析师工具调用轮数，默认 8。 |

## PostgreSQL 部署

默认 SQLite 适合个人使用。多人使用、生产部署或需要托管备份时，可以通过 `DATABASE_URL` 切换到 PostgreSQL。

```bash
fly secrets set DATABASE_URL="postgresql+psycopg2://user:password@your-pg-host:5432/dbname"
```

设置 `DATABASE_URL` 后，系统会忽略 SQLite 的 `DATA_DIR`，并在首次启动时创建所需表结构。

## Fly.io 部署

Docker 镜像会先构建 React 前端，再由 FastAPI 同源托管前端静态文件和后端 API。

```bash
fly launch --no-deploy
fly volumes create data --size 1 --region nrt

fly secrets set ENV="production"
fly secrets set SECRET_KEY="replace-with-a-long-random-string"
fly secrets set APP_BASE_URL="https://your-app.fly.dev"
fly secrets set APP_ENCRYPTION_KEY="<your-fernet-key>" ALLOW_SYSTEM_AI_FALLBACK="false"

fly deploy
```

需要真实邮件服务时，再配置 `EMAIL_ENABLED`、`EMAIL_FROM`、`SMTP_HOST`、`SMTP_PORT`、`SMTP_USERNAME`、`SMTP_PASSWORD` 等 SMTP 变量。

多 Agent 会在镜像内安装固定版本的 TradingAgents（独立 venv）。它比标准研究更吃内存，Fly.io 建议：

```bash
fly scale memory 1024
```

如果不使用多 Agent，可以用 `fly deploy --build-arg INSTALL_TRADINGAGENTS=0` 缩小镜像并跳过安装；此时界面会明确提示引擎不可用，标准研究不受影响。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 后端 | FastAPI、SQLModel、SQLite、PostgreSQL、JWT、akshare、CoinGecko、OpenAI-compatible AI clients |
| 前端 | React 18、Vite、Ant Design 5、ECharts、React Router、Axios、react-markdown、remark-gfm |
| 部署 | Docker 多阶段构建、Fly.io、持久化 volume |
| 测试 | Pytest、HTTPX、Node 前端接口测试、前端构建检查 |

## 项目结构

```text
FinancialSystem/
├── backend/                    FastAPI 后端
│   ├── main.py                 应用入口、路由挂载、静态前端托管
│   ├── models.py               SQLModel 表、Schema 和资产计算
│   ├── database.py             数据库连接、初始化和轻量迁移
│   ├── position.py             交易回放和 derived 持仓计算
│   ├── import_service.py       CSV 导入预览、提交和去重
│   ├── reconciliation_service.py
│   ├── ai_berkshire_loader.py   投研模板与 skill 加载
│   ├── research_*.py            研究服务、结构化摘要、追问、事件、用量与标的解析
│   ├── tradingagents_*.py       TradingAgents 适配层与独立 Worker
│   ├── importers/              富途、IBKR、通用导入解析器
│   ├── routers/                API 路由
│   └── tests/                  后端测试
├── frontend/                   React 前端
│   └── src/
│       ├── api/                Axios API 层
│       ├── pages/              Dashboard、平台、交易、AI、日志等页面
│       ├── displaySettings.jsx 全局展示币种
│       └── colorScheme.jsx     涨跌颜色偏好
├── docs/                       设计文档和历史方案
├── Dockerfile                  前后端一体化镜像
├── fly.toml                    Fly.io 部署配置
├── dev.py                      跨平台开发脚本
└── TECHNICAL_ROADMAP.md        技术路线图
```

## 文档导航

- [Architecture](ARCHITECTURE.md)：工程结构、核心数据模型、API 和关键数据流。
- [Technical Roadmap](TECHNICAL_ROADMAP.md)：后续工程路线、优先级和验收标准。
- [Changelog](CHANGELOG.md)：已完成能力和版本变化。
- [AI Research & TradingAgents](docs/ai-research-and-tradingagents.md)：AI 投研 v2、多 Agent 接入、配置、迁移、回滚与验证边界。
- [Phase 1 Import Design](docs/superpowers/specs/2026-06-28-phase1-import-reconciliation-design.md)：导入与对账系统设计。

## 开发验证

在已安装后端依赖的 Python 环境中执行 `cd backend`、`python -m pytest tests/ -q`。前端执行 `cd frontend`、`npm ci`、`npm test` 和 `npm run build`。GitHub Actions 会检查后端测试、前端测试与构建，以及 Docker 镜像构建。

## 免责声明

本项目仅用于个人资产记录、投研辅助和工程学习。行情数据、汇率数据和 AI 生成内容可能延迟、不完整或错误。项目中的任何内容都不构成投资建议。

## License

Released under the [MIT License](LICENSE).
