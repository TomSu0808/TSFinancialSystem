# TSFinancialSystem

<div align="center">

**一个可自部署的多账户、多币种个人资产管理与 AI 投研工作台。**

[在线体验](https://tsfinancialsystem.fly.dev/) · [English](README.md) · [架构说明](ARCHITECTURE.md) · [技术路线图](TECHNICAL_ROADMAP.md) · [更新日志](CHANGELOG.md)

[![CI](https://github.com/TomSu0808/TSFinancialSystem/actions/workflows/ci.yml/badge.svg)](https://github.com/TomSu0808/TSFinancialSystem/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.128-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)](Dockerfile)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

TSFinancialSystem 将资产组合、交易流水、行情与汇率、现金账本、投资决策日志和 AI 投研整合到一个私有 Web 应用中。它适合希望看懂自己的持仓、保留可追溯研究记录，并掌控资产数据的个人投资者。

> 本项目用于个人资产记录、投研辅助和工程学习，不构成投资建议。

## 能做什么

| 模块 | 能力 |
| --- | --- |
| **资产组合** | 管理券商、银行、钱包、基金、股票、债券、加密货币、现金和多币种展示口径。 |
| **交易账本** | 将买入、卖出、分红、入金、出金和现金校准流水回放为持仓、成本、已实现盈亏和现金余额。 |
| **AI 投研** | 研究公司、分析财报、检查持仓和复查投资逻辑；支持 GPT 与 DeepSeek，DeepSeek 模型为 `deepseek-flash`（V4.1-Flash-1017）。 |
| **复盘闭环** | 保存结构化报告、来源、追问、版本更新、行动项和投资决策笔记。 |

## 为什么做它

| 没有私有工作台 | 使用 TSFinancialSystem |
| --- | --- |
| 资产分散在券商、银行和表格中。 | 在一个工作台统一管理账户、持仓、现金和交易。 |
| 持仓和收益依靠手工计算。 | 根据交易流水计算持仓、成本、已实现盈亏和现金变动。 |
| 投研内容散落在聊天记录和笔记中。 | 报告、来源、追问、版本和跟踪事项保持关联。 |
| AI 分析可能依赖过时知识。 | 可选联网检索，把带日期的外部搜索结果加入研究上下文。 |
| 资产数据依赖第三方产品。 | 使用 SQLite 或 PostgreSQL 自行部署和管理数据。 |

## 核心功能

### 资产与交易

- 管理券商、银行、钱包和自定义平台等多种资产账户。
- 支持 CNY、USD、HKD 等币种，并可切换展示币种。
- 根据交易流水计算持仓、移动加权成本、已实现盈亏、分红和清仓状态。
- 按账户和币种管理现金，支持卖出到账、提现、现金校准和透支校验。
- 支持 A 股、港股、美股、基金、加密货币和 USD/CNY 行情与汇率刷新。
- 支持富途、IBKR 和通用 CSV 导入，包含预览校验、去重、提交和对账。

### AI 投研

- 以任务为入口研究公司、分析财报、检查持仓和复查投资逻辑。
- 支持 GPT 与 DeepSeek，DeepSeek 默认使用 `deepseek-flash`。
- 支持可选联网检索：DeepSeek 使用 Search API，GPT 使用 OpenAI 联网工具。
- 生成区分事实、分析、假设、风险和跟踪事项的结构化报告。
- 在报告内追问，追问记录独立保存，不覆盖原报告。
- 生成带版本链的研究更新，并保存来源和获取时间。
- 可选固定版本 TradingAgents 多 Agent 流程，运行于隔离 Worker 子进程中。

### 安全与部署

- Docker 自部署，FastAPI 后端和 React 前端由同一镜像提供服务。
- 默认使用 SQLite，也可以通过 `DATABASE_URL` 使用 PostgreSQL。
- 支持 JWT 鉴权、多用户数据隔离、邮箱验证、找回密码和 BYOK API Key。
- 仓库不需要提交 `.env`、账户数据库、备份文件或 API Key。

## 适合谁

- 同时使用多个券商、银行、钱包或基金账户的投资者。
- 持有 CNY、USD、HKD 等多币种资产的人。
- 希望由交易流水驱动持仓和收益计算的人。
- 希望长期保存投研报告、投资逻辑和复盘记录的人。
- 希望自部署并掌控资产数据的人。

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+

### 本地运行

```bash
git clone https://github.com/TomSu0808/TSFinancialSystem.git
cd TSFinancialSystem
python dev.py start
```

启动脚本会准备后端环境，启动 FastAPI 和 Vite，并打开应用。

| 服务 | 地址 |
| --- | --- |
| 前端 | <http://localhost:5173> |
| 后端 API | <http://localhost:8000> |
| API 文档 | <http://localhost:8000/docs> |

停止本地服务：

```bash
python dev.py stop
```

只准备依赖、不启动应用：

```bash
python dev.py setup
```

## 配置应用

本地开发时复制示例配置：

```bash
cp backend/.env.example backend/.env
```

本地将敏感配置放在 `backend/.env`，生产环境使用部署平台的 secret 管理。不要提交 `.env`、`data.db`、账户备份或 API Key。

常用配置：

| 配置项 | 说明 |
| --- | --- |
| `ENV` | 设置为 `production` 后启用生产配置检查。 |
| `DATA_DIR` | SQLite 数据目录，例如 Fly.io 上的 `/data`。 |
| `DATABASE_URL` | 可选 PostgreSQL 连接串；未设置时使用 SQLite。 |
| `ALLOW_REGISTRATION` | 是否允许公开注册，默认 `true`。 |
| `APP_BASE_URL` | 邮箱验证和找回密码使用的公开地址。 |
| `APP_ENCRYPTION_KEY` | 生产环境必填，用于加密用户 AI API Key。 |
| `AI_PROVIDER` | 默认 Provider，可选 `gpt` 或 `deepseek`。 |
| `DEEPSEEK_MODEL` | 默认 `deepseek-flash`，即 DeepSeek-V4.1-Flash-1017 API 模型。 |
| `DEEPSEEK_SEARCH_ENABLED` | 是否启用 DeepSeek Search API 联网检索，默认 `true`。 |
| `RESEARCH_MAX_LLM_CALLS` | 单任务模型调用上限，标准研究默认 12，多 Agent 默认 60。 |
| `RESEARCH_MAX_OUTPUT_TOKENS` | 单任务输出 token 上限，默认 120000。 |
| `RESEARCH_MAX_SECONDS` | 单任务时间上限，标准研究默认 1800 秒，多 Agent 默认 3600 秒。 |
| `AI_PRICE_TABLE_JSON` | 可选 Provider/模型价格表，用于费用显示和预算限制。 |

完整配置见 [`backend/.env.example`](backend/.env.example)。

## AI 投研与最新资料

开启联网检索后，系统会将检索请求、查询结果、日期、URL 和获取时间保存到报告中。来源会标注为系统抓取，不会直接标记为独立核验。联网结果不能代替查看公司公告、交易所公告或监管披露。

由于 DeepSeek Responses API 的 web-search 工具不适用于 `deepseek-flash`，DeepSeek 联网检索使用独立的 Search API。Search API 按请求单独计费；不需要联网时可以关闭 `DEEPSEEK_SEARCH_ENABLED`。

详细的投研流程、TradingAgents 接入、预算限制、迁移行为和验证边界见 [`docs/ai-research-and-tradingagents.md`](docs/ai-research-and-tradingagents.md)。

## 部署到 Fly.io

仓库包含 [`fly.toml`](fly.toml) 和 Dockerfile，可部署前后端一体化应用。

```bash
fly launch --no-deploy
fly volumes create data --size 1 --region nrt

fly secrets set ENV="production"
fly secrets set SECRET_KEY="replace-with-a-long-random-string"
fly secrets set APP_BASE_URL="https://your-app.fly.dev"
fly secrets set APP_ENCRYPTION_KEY="<your-fernet-key>"
fly secrets set ALLOW_SYSTEM_AI_FALLBACK="false"

fly deploy
```

多 Agent 研究建议至少分配 1 GB 内存：

```bash
fly scale memory 1024
```

如果不使用多 Agent，可以跳过 TradingAgents 镜像层：

```bash
fly deploy --build-arg INSTALL_TRADINGAGENTS=0
```

## 文档导航

- [架构说明](ARCHITECTURE.md)：工程结构、数据模型、API 和数据流。
- [AI 投研与 TradingAgents](docs/ai-research-and-tradingagents.md)：投研流程、联网检索、多 Agent 执行、配置和限制。
- [技术路线图](TECHNICAL_ROADMAP.md)：工程优先级和验收标准。
- [更新日志](CHANGELOG.md)：已完成的功能和行为变化。

## 开发验证

后端：

```bash
cd backend
python -m pytest tests/ -q
```

前端：

```bash
cd frontend
npm ci
npm test
npm run build
```

GitHub Actions 还会检查后端测试、前端测试与构建，以及 Docker 镜像构建。

## License

Released under the [MIT License](LICENSE)。
