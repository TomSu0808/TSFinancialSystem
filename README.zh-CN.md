<div align="center">

# TSFinancialSystem

**一个可自部署的多币种个人资产管理与 AI 投研系统。**

[English](README.md) ·
[线上访问](https://tsfinancialsystem.fly.dev/) ·
[架构说明](ARCHITECTURE.md) ·
[更新日志](CHANGELOG.md)

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.128-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-5-646CFF?logo=vite&logoColor=white)](https://vitejs.dev/)
[![Ant Design](https://img.shields.io/badge/Ant%20Design-5-0170FE?logo=antdesign&logoColor=white)](https://ant.design/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)](Dockerfile)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

## 项目定位

TSFinancialSystem 用来在一个私有 Web 应用里管理股票、基金、债券、加密货币和现金。它按账户和币种组织资产，支持行情刷新、USD/CNY 汇率换算、交易流水驱动持仓、净值曲线、资产配置图，以及 AI 辅助投研报告。

它适合希望自己掌控资产数据，又想要一个清晰投资驾驶舱的个人投资者。

## 线上体验

**<https://tsfinancialsystem.fly.dev/>**

线上版本支持注册、登录、多用户数据隔离，并通过 Fly.io 提供 HTTPS。

## 截图

| 总览 | 资产明细 |
| --- | --- |
| ![总览](01-dashboard.png) | ![资产明细](02-platform-detail.png) |

## 核心功能

| 模块 | 能做什么 |
| --- | --- |
| 资产总览 | 查看总资产、今日涨跌、总收益、未实现 / 已实现盈亏、分红收益和净值走势；「今日归因 / 数据状态」卡片展示涨跌贡献前 5、收益组成拆分和行情刷新状态 |
| 全局显示货币 | 在 USD / CNY 间全局切换，所有页面、盈亏和图表同步更新，并在重新登录后保持设置 |
| 多币种资产 | 支持 CNY、USD、HKD 持仓；金额会按当前显示货币和汇率换算 |
| 账户管理 | 按券商、银行、钱包或自定义账户分组，例如富途、盈透、老虎、银行卡、加密钱包 |
| 行情与汇率 | 支持 A 股、港股、美股、基金、加密货币和 USD/CNY 汇率刷新 |
| 交易驱动持仓 | 买入 / 卖出 / 分红流水自动更新数量、移动加权成本、已实现盈亏和清仓状态 |
| 交易搜索与筛选 | 按类型、币种、平台、关键词（名称 / 代码 / 备注）和日期范围过滤交易流水 |
| CSV 批量导入 | 使用标准模板 CSV 批量导入交易，导入前逐行预览校验结果，buy/sell/dividend 自动同步 derived 持仓 |
| 投资决策日志 | 笔记升级为结构化决策记录：买入逻辑、风险点、复盘、行动项、观察，可关联标的或持仓，支持状态跟踪（跟踪中 / 已解决 / 已证伪 / 已归档） |
| AI 报告生成跟踪事项 | 一键从 AI 报告「行动项」章节提取并保存到决策日志，自动关联标的和来源报告 |
| 持仓研究摘要 | 持仓详情页新增「研究记录」抽屉，展示该标的的买入逻辑、风险点、行动项和 AI 报告 |
| 定时自动刷新 | 可配置每日定时刷新行情、汇率和净值快照；支持时区和启动时立即运行；Dashboard 提供「立即运行」入口 |
| 站内提醒 | 规则化提醒：价格阈值、今日涨跌幅、仓位占比、行情过期、刷新失败；事件展示在 Dashboard 和专属提醒页 |
| PostgreSQL 可选部署 | 通过 `DATABASE_URL` 切换至 PostgreSQL，适合生产环境和多人使用；默认仍为 SQLite |
| 手动资产 | 现金、债券、私募、无法自动抓价的资产可以直接手动维护市值 |
| 投资笔记 | 记录投资决策、复盘、观察清单和研究备忘 |
| AI 投研工作台 | 使用 GPT、DeepSeek、GLM 或 Claude 生成中文 / 英文投研报告；报告支持 Markdown、表格、代码块和引用渲染 |
| BYOK | 每个用户可在个人资料 → AI 设置中配置自己的 API Key，系统不需要共用密钥 |
| 隐私与安全 | 金额打码、深色模式、邮箱验证、安全问题找回密码、JWT 鉴权、多用户数据隔离 |
| 移动端适配 | 小屏幕使用抽屉导航，表单、卡片和表格按移动端宽度重新排版 |
| 自部署 | 一个 Docker 镜像同时托管 React 前端和 FastAPI 后端，SQLite 数据持久化到 Fly.io volume |

## 使用流程

1. 创建券商、银行、钱包等账户。
2. 添加手动持仓，或录入买入、卖出、分红等交易流水。
3. 按需刷新行情和汇率，也可以开启进入总览自动刷新。
4. 查看总资产、收益、资产配置和净值曲线，并全局切换美元 / 人民币显示。
5. 记录投资笔记，生成中文或英文 AI 投研报告。
6. 需要迁移或备份时，导出整账 JSON。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 后端 | FastAPI、SQLModel、SQLite、JWT auth、akshare、CoinGecko、OpenAI-compatible AI clients |
| 前端 | React 18、Vite、Ant Design 5、ECharts、React Router、Axios、react-markdown + remark-gfm |
| 部署 | Docker 多阶段构建、Fly.io、持久化 volume |
| 数据 | 默认 SQLite，预留 `DATABASE_URL` 方便后续迁移 |

## 数据来源

| 数据 | 来源 | 说明 |
| --- | --- | --- |
| A 股、港股、美股、场内基金 | akshare / 东方财富快照 | 免费数据，通常有延迟 |
| 场外基金 | akshare 基金净值 | 按基金代码获取最近净值 |
| 加密货币 | CoinGecko 免费接口 | 支持常见 symbol 和 CoinGecko ID |
| USD/CNY 汇率 | open.er-api.com | 失败时回退到中行数据 |

## 本地启动

**前置要求：** Python 3.10+、Node.js 18+

```bash
git clone https://github.com/TomSu0808/TSFinancialSystem.git
cd TSFinancialSystem
python dev.py start
```

启动脚本会自动创建后端虚拟环境、安装依赖、启动 FastAPI 和 Vite，并打开浏览器。

| 服务 | 地址 |
| --- | --- |
| 前端 | <http://localhost:5173> |
| 后端 API | <http://localhost:8000> |
| API 文档 | <http://localhost:8000/docs> |

```bash
python dev.py stop   # 停止开发服务
```

**手动启动：**

```bash
# 后端
cd backend
python -m venv .venv
source .venv/bin/activate          # macOS/Linux
# .venv\Scripts\activate           # Windows
pip install -r requirements.txt
uvicorn main:app --reload
```

```bash
# 前端，另开一个终端
cd frontend
npm install
npm run dev
```

## 配置项

本地开发时，复制 `backend/.env.example` 为 `backend/.env`。

| 变量 | 作用 |
| --- | --- |
| `SECRET_KEY` | JWT 签名密钥，生产环境必须设置为固定随机值 |
| `ENV` | 运行环境，`production` 时启用启动配置检查 |
| `DATA_DIR` | SQLite 数据目录，例如 Fly.io 上的 `/data` |
| `DATABASE_URL` | 可选数据库连接 URL |
| `ALLOW_REGISTRATION` | 是否开放注册，默认 `true` |
| `APP_BASE_URL` | 对外访问地址，用于生成邮箱验证和密码重置链接，生产必填 |
| `EMAIL_ENABLED` | `false`（默认）时把验证链接打印到日志；`true` 时通过 SMTP 发送邮件 |
| `EMAIL_FROM` | 发件人地址 |
| `SMTP_HOST` | SMTP 服务器地址 |
| `SMTP_PORT` | SMTP 端口，默认 587 |
| `SMTP_USERNAME` | SMTP 用户名 |
| `SMTP_PASSWORD` | SMTP 密码 |
| `SMTP_TLS` | `true` 使用 SSL/TLS，`false` 使用 STARTTLS |
| `APP_ENCRYPTION_KEY` | **生产环境必填**。用于加密用户 API Key 的 Fernet 密钥。生成命令：`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`。更换此密钥后，已保存的用户 API Key 将无法解密。 |
| `ALLOW_SYSTEM_AI_FALLBACK` | `false`（默认）：用户必须配置自己的 API Key。`true`：用户没有 Key 时可回退到系统全局 Key |
| `AI_PROVIDER` | 默认 AI 提供方：`gpt`、`deepseek`、`glm` 或 `claude` |
| `DEEPSEEK_API_KEY` | 系统全局 DeepSeek Key |
| `OPENAI_API_KEY` | 系统全局 OpenAI Key |
| `GLM_API_KEY` | 系统全局 GLM Key |
| `ANTHROPIC_API_KEY` | 系统全局 Claude Key |
| `FX_REFRESH_INTERVAL_SECONDS` | USD/CNY 汇率缓存时间，默认 21600 秒 |
| `AUTO_REFRESH_ENABLED` | `false`（默认）：关闭定时刷新。`true`：启动后台每日刷新任务 |
| `AUTO_REFRESH_TIME` | 每日触发时间，格式 `HH:MM`，默认 `08:30` |
| `AUTO_REFRESH_INTERVAL_HOURS` | 刷新间隔小时数，默认 `24` |
| `AUTO_REFRESH_TIMEZONE` | 时区，任意 `zoneinfo` 字符串，默认 `Asia/Shanghai` |
| `AUTO_REFRESH_ON_STARTUP` | `false`（默认）：等待下次计划时间。`true`：启动后立即执行一次 |
| `ALERTS_ENABLED` | `true`（默认）：每次刷新后评估提醒规则。`false`：完全关闭 |
| `DATABASE_URL` | 完整数据库连接串，留空默认 SQLite。PostgreSQL 示例：`postgresql+psycopg2://user:password@host:5432/dbname` |

## PostgreSQL 部署（可选）

默认使用 SQLite，适合个人本地使用。需要生产环境或多人共用时，可通过 `DATABASE_URL` 切换至 PostgreSQL。

**Fly.io 设置示例：**

```bash
fly secrets set DATABASE_URL="postgresql+psycopg2://user:password@your-pg-host:5432/dbname"
```

**本地开发使用 PostgreSQL：**

```bash
export DATABASE_URL="postgresql+psycopg2://user:password@localhost:5432/tsfinancial"
uvicorn main:app --reload
```

设置 `DATABASE_URL` 后，`DATA_DIR`（SQLite 路径）将被忽略。所有表格由 `SQLModel.metadata.create_all` 在首次启动时自动创建。

## 部署到 Fly.io

仓库会构建成一个 Docker 镜像。FastAPI 会托管编译后的 React 前端，因此线上前后端同源，不需要单独部署前端。

```bash
fly launch --no-deploy
fly volumes create data --size 1 --region nrt

# 基础必填
fly secrets set ENV="production"
fly secrets set SECRET_KEY="replace-with-a-long-random-string"
fly secrets set APP_BASE_URL="https://your-app.fly.dev"

# BYOK 加密密钥（必填）
fly secrets set APP_ENCRYPTION_KEY="<生成的-fernet-key>" ALLOW_SYSTEM_AI_FALLBACK="false"

# 系统全局 AI Key（可选，仅 ALLOW_SYSTEM_AI_FALLBACK=true 时使用）
fly secrets set DEEPSEEK_API_KEY="your-key" AI_PROVIDER="deepseek"

# 邮件服务（可选；未配置时验证链接会出现在 fly logs）
fly secrets set EMAIL_ENABLED="true" \
  EMAIL_FROM="noreply@yourdomain.com" \
  SMTP_HOST="smtp.example.com" \
  SMTP_PORT="587" \
  SMTP_USERNAME="your-user" \
  SMTP_PASSWORD="your-password"

fly deploy
```

本地 `.env` 文件不会上传到 Fly.io。生产环境密钥必须通过 `fly secrets set` 设置。

## 项目结构

```text
FinancialSystem/
├─ backend/
│  ├─ main.py                     FastAPI 入口和静态前端托管
│  ├─ models.py                   SQLModel 表、schema 和资产计算逻辑
│  ├─ database.py                 数据库引擎、初始化和轻量迁移
│  ├─ position.py                 交易流水重放和 derived 持仓状态
│  ├─ price_provider.py           行情数据源（akshare、CoinGecko）
│  ├─ fx_provider.py              USD/CNY 汇率数据源
│  ├─ ai_client.py                GPT / DeepSeek / GLM / Claude 客户端抽象
│  ├─ research_prompt_builder.py  AI 投研 prompt 组装和 Markdown 格式约束
│  ├─ email_service.py            SMTP 邮件（验证、重置密码）
│  ├─ rate_limit.py               进程内滑动窗口限流
│  └─ routers/                    API 路由模块
├─ frontend/
│  └─ src/
│     ├─ App.jsx                  布局、路由和全局设置
│     ├─ displaySettings.jsx      全局显示货币和汇率换算工具
│     ├─ colorScheme.jsx          涨跌颜色方案（红涨或绿涨）
│     ├─ api/index.js             Axios API 层
│     └─ pages/                   总览、资产、资产明细、交易、投研、笔记、登录
├─ Dockerfile                     Docker 多阶段构建
├─ fly.toml                       Fly.io 部署配置
├─ dev.py                         跨平台开发启动器
├─ 01-dashboard.png               总览截图
└─ 02-platform-detail.png         资产明细截图
```

## 路线图

- [x] 多用户 JWT 登录鉴权
- [x] Docker 和 Fly.io 部署
- [x] 交易流水驱动持仓
- [x] 投资笔记
- [x] 整账 JSON 备份和恢复
- [x] 隐私模式和深色主题
- [x] AI 辅助投研工作台（GPT、DeepSeek、GLM、Claude）
- [x] Markdown 渲染的 AI 报告（GFM 表格、代码块、引用）
- [x] 邮箱验证、找回密码、安全问题恢复
- [x] BYOK：用户级 AI API Key 加密管理
- [x] 全局显示货币（USD/CNY，跨页面同步并持久化）
- [x] 移动端响应式布局（抽屉导航、自适应表单、可滚动表格）
- [x] 交易搜索与筛选（类型、币种、平台、关键词、日期范围）
- [x] CSV 批量导入（含逐行预览校验）
- [x] Dashboard 今日归因（涨跌贡献、收益组成、行情状态）
- [x] 投资决策日志（类型、状态、标的关联、tags）
- [x] AI 报告生成跟踪事项（一键提取行动项到决策日志）
- [x] 持仓研究摘要抽屉（thesis / 风险 / 行动项 / AI 报告）
- [x] AI 报告结构化输出（六大必备章节：结论 / 假设 / 风险 / 待验证 / 指标 / 行动项）
- [x] 定时自动刷新行情/汇率/快照（可配置时间和时区）
- [x] 站内提醒系统（价格/涨跌幅/仓位/行情过期/刷新失败规则）
- [x] PostgreSQL 可选部署（通过 DATABASE_URL 切换）
- [ ] 富途 / IBKR / 老虎等券商 CSV 格式适配
- [ ] 富途、盈透等券商 API 同步

## 免责声明

本项目用于个人资产记录和投研日志管理。行情数据和 AI 生成内容可能延迟、不完整或存在错误，不构成任何投资建议。

## License

Released under the [MIT License](LICENSE).
