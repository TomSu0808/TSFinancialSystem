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

它不是简单记账工具，而是一个个人投资管理工作台：把资产、交易、复盘、提醒和 AI 投研放在同一个流程里。

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
| 多币种资产总览 | 支持 CNY、USD、HKD 等币种，并可在 CNY / USD 展示口径之间切换。 |
| 交易驱动持仓 | 买入、卖出、分红等交易流水自动更新 derived 持仓、移动加权成本、已实现盈亏和清仓状态。 |
| Dashboard 总览 | 查看总资产、今日涨跌、总收益、未实现 / 已实现盈亏、资产配置、净值曲线和数据状态。 |
| 行情与汇率刷新 | 支持 A 股、港股、美股、基金、加密货币和 USD/CNY 汇率刷新。 |
| CSV 导入与对账 | 支持富途、IBKR、通用 CSV 导入流程；导入前预览校验，导入后生成对账结果。 |
| 现金账本 | 入金、出金自动维护平台和币种维度的现金持仓。 |
| 投资决策日志 | 用结构化笔记记录买入逻辑、风险、复盘、行动项和观察事项，并关联标的或持仓。 |
| AI 投研工作台 | 支持 GPT、DeepSeek、GLM、Claude 等 OpenAI-compatible Provider 生成中文或英文投研报告。 |
| AI 行动项闭环 | 从 AI 报告中提取行动项，保存到投资决策日志，并持续跟踪状态。 |
| 提醒系统 | 支持价格阈值、日涨跌幅、仓位占比、行情过期和自动刷新失败等提醒。 |
| 隐私与安全 | 支持 JWT 鉴权、多用户数据隔离、金额打码、深色模式、邮箱验证、找回密码和 BYOK。 |
| 自部署 | 一个 Docker 镜像同时托管 React 前端和 FastAPI 后端，默认 SQLite，也可通过 `DATABASE_URL` 使用 PostgreSQL。 |

## 典型使用流程

1. 注册账号并创建平台，例如券商、银行、钱包或自定义账户。
2. 添加手动持仓，或录入买入、卖出、分红、入金、出金等交易流水。
3. 需要批量迁移时，通过 CSV 导入历史交易，并查看预览校验和对账结果。
4. 刷新行情和汇率，或在 Dashboard 中开启定时自动刷新。
5. 在 Dashboard 查看总资产、收益、资产配置、净值曲线和数据状态。
6. 为关键持仓生成 AI 投研报告，并把行动项沉淀到投资决策日志。
7. 需要迁移或备份时，导出完整账户 JSON。

## 页面概览

| 页面 | 用途 |
| --- | --- |
| Dashboard | 总资产、今日涨跌、收益拆分、资产配置、净值曲线、数据状态和自动刷新入口。 |
| 平台管理 | 按券商、银行或钱包组织资产，并查看每个平台下的持仓。 |
| 持仓详情 | 管理手动资产，查看交易生成的 derived 持仓、成本、盈亏和研究摘要。 |
| 交易流水 | 记录、筛选、搜索买入 / 卖出 / 分红 / 入金 / 出金，并执行 CSV 批量导入。 |
| AI 投研 | 选择模板、指定标的或组合，生成结构化 Markdown 投研报告。 |
| 决策日志 | 记录投资逻辑、风险、复盘和行动项，并关联标的、持仓和 AI 报告。 |
| 提醒中心 | 管理提醒规则，查看触发记录和刷新失败事件。 |

## 数据来源

| 数据类型 | 来源 | 说明 |
| --- | --- | --- |
| A 股、港股、美股、场内基金 | akshare / 东方财富快照 | 免费数据源，可能延迟或不完整。 |
| 场外基金 | akshare 基金净值 | 按基金代码获取最新净值。 |
| 加密货币 | CoinGecko Free API | 支持常见 symbol 和 CoinGecko ID。 |
| USD/CNY 汇率 | open.er-api.com，失败时回退到中国银行数据 | 用于 CNY / USD 展示口径换算。 |
| AI 报告 | 用户配置的 AI Provider | 支持用户自带 API Key，不构成投资建议。 |

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
| `ALERTS_ENABLED` | 是否启用提醒规则计算。 |

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

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 后端 | FastAPI、SQLModel、SQLite、PostgreSQL、JWT、akshare、CoinGecko、OpenAI-compatible AI clients |
| 前端 | React 18、Vite、Ant Design 5、ECharts、React Router、Axios、react-markdown、remark-gfm |
| 部署 | Docker 多阶段构建、Fly.io、持久化 volume |
| 测试 | Pytest、HTTPX、前端构建检查 |

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
│   ├── importers/              富途、IBKR、通用导入解析器
│   ├── routers/                API 路由
│   └── tests/                  后端测试
├── frontend/                   React 前端
│   └── src/
│       ├── api/                Axios API 层
│       ├── pages/              Dashboard、平台、交易、AI、日志、提醒等页面
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
- [Phase 1 Import Design](docs/superpowers/specs/2026-06-28-phase1-import-reconciliation-design.md)：导入与对账系统设计。

## 免责声明

本项目仅用于个人资产记录、投研辅助和工程学习。行情数据、汇率数据和 AI 生成内容可能延迟、不完整或错误。项目中的任何内容都不构成投资建议。

## License

Released under the [MIT License](LICENSE).
