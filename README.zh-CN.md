<div align="center">

# TSFinancialSystem

**一个可自部署的多币种个人资产管理与投资研究系统。**

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

TSFinancialSystem 用来在一个私有 Web 应用里管理股票、基金、债券、加密货币、现金和投资笔记。它按平台和币种组织资产，支持实时行情、美元/人民币汇率、交易流水驱动持仓、净值曲线、资产配置图，以及 AI 辅助投研报告。

它适合想要自己掌控数据、又希望有一个清晰资产驾驶舱的个人投资者。

## 线上地址

项目已部署在：

**https://tsfinancialsystem.fly.dev/**

线上版本支持注册、登录、多用户数据隔离，并通过 Fly.io 提供 HTTPS 访问。

## 核心功能

| 模块 | 能做什么 |
|---|---|
| 资产总览 | 查看总资产、今日涨跌、总收益、未实现/已实现盈亏、分红收益和净值走势 |
| 多币种资产 | 支持 CNY、USD、HKD，并按 USD/CNY 汇率折算 |
| 平台管理 | 按券商、银行、钱包或自定义账户分组，例如富途、盈透、老虎、银行卡、加密钱包 |
| 实时数据 | 支持 A 股、港股、美股、基金、加密货币和汇率数据 |
| 交易驱动持仓 | 买入、卖出、分红流水会自动更新数量、移动加权成本、已实现盈亏和清仓状态 |
| 手动资产 | 现金、债券、私募、无法抓价的资产可以手动维护市值 |
| 投资笔记 | 记录投资决策、复盘、观察清单和研究备忘 |
| AI 投研工作台 | 使用 GPT、DeepSeek、GLM 或 Claude 兼容接口生成投研 prompt 和报告 |
| 隐私能力 | 登录鉴权、用户数据隔离、金额打码、深色模式、整账备份和恢复 |
| 自部署 | 一个 Docker 镜像同时托管 React 前端和 FastAPI 后端，SQLite 数据持久化到 Fly.io volume |

## 使用流程

1. 创建券商、银行、钱包等资产平台。
2. 添加手动持仓，或录入买入、卖出、分红等交易流水。
3. 手动刷新行情和汇率。
4. 查看总资产、收益、资产配置和净值曲线。
5. 记录投资笔记，并生成 AI 辅助投研报告。
6. 需要迁移或备份时，导出整账 JSON。

## 技术栈

| 层级 | 技术 |
|---|---|
| 后端 | FastAPI、SQLModel、SQLite、JWT auth、akshare、CoinGecko、OpenAI-compatible AI clients |
| 前端 | React 18、Vite、Ant Design 5、ECharts、React Router、Axios |
| 部署 | Docker 多阶段构建、Fly.io、持久化 volume |
| 数据 | 默认 SQLite，预留 `DATABASE_URL` 方便后续迁移 |

## 数据来源

| 数据 | 来源 | 说明 |
|---|---|---|
| A 股、港股、美股、场内基金 | akshare / 东方财富快照 | 免费数据，通常有延迟 |
| 场外基金 | akshare 基金净值 | 按基金代码获取最近净值 |
| 加密货币 | CoinGecko 免费接口 | 支持常见 symbol 和 CoinGecko id |
| USD/CNY 汇率 | open.er-api.com | 失败时回退到中行数据 |

## 本地启动

前置要求：

- Python 3.10+
- Node.js 18+

```bash
git clone https://github.com/TomSu0808/TSFinancialSystem.git
cd TSFinancialSystem
python dev.py start
```

启动脚本会自动创建后端虚拟环境、安装依赖、启动 FastAPI 和 Vite，并打开浏览器。

| 服务 | 地址 |
|---|---|
| 前端 | http://localhost:5173 |
| 后端 API | http://localhost:8000 |
| API 文档 | http://localhost:8000/docs |

停止开发服务：

```bash
python dev.py stop
```

手动启动：

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

```bash
cd frontend
npm install
npm run dev
```

## 配置项

本地开发时，复制 `backend/.env.example` 为 `backend/.env`。

常用环境变量：

| 变量 | 作用 |
|---|---|
| `SECRET_KEY` | JWT 签名密钥，生产环境必须设置为固定随机值 |
| `ENV` | 运行环境，`production` 时启动配置自检（缺失关键配置则退出） |
| `DATA_DIR` | SQLite 数据目录，例如 Fly.io 上的 `/data` |
| `DATABASE_URL` | 可选数据库连接 URL |
| `ALLOW_REGISTRATION` | 是否开放注册，默认 `true` |
| `APP_BASE_URL` | 对外访问地址，用于生成邮件中的验证/重置链接，生产必填 |
| `EMAIL_ENABLED` | `false`（默认）时打印链接到控制台；`true` 时通过 SMTP 发送。仅在用户绑定了邮箱时才会用到 |
| `EMAIL_FROM` | 发件人地址 |
| `SMTP_HOST` | SMTP 服务器地址 |
| `SMTP_PORT` | SMTP 端口，默认 587 |
| `SMTP_USERNAME` | SMTP 用户名 |
| `SMTP_PASSWORD` | SMTP 密码 |
| `SMTP_TLS` | `true` 使用 SSL/TLS，`false` 使用 STARTTLS，默认 `true` |
| `APP_ENCRYPTION_KEY` | **生产环境必填**。用于加密用户 API Key 的 Fernet 密钥。生成命令：`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`。**警告**：更换此密钥后，已保存的用户 API Key 将无法解密，需让用户重新配置。 |
| `ALLOW_SYSTEM_AI_FALLBACK` | `false`（默认）：用户必须在个人资料 → AI 设置中配置自己的 Key 才能使用 AI 投研。`true`：用户没有 Key 时可回退到系统全局 Key（站长自用模式）。 |
| `AI_PROVIDER` | 默认 AI 提供方：`gpt`、`deepseek`、`glm` 或 `claude` |
| `DEEPSEEK_API_KEY` | 系统全局 DeepSeek Key（`ALLOW_SYSTEM_AI_FALLBACK=true` 时或站长自用） |
| `OPENAI_API_KEY` | 系统全局 GPT/OpenAI Key |
| `GLM_API_KEY` | 系统全局 GLM Key |
| `ANTHROPIC_API_KEY` | 系统全局 Claude Key |
| `FX_REFRESH_INTERVAL_SECONDS` | USD/CNY 汇率缓存时间，默认 21600 秒 |

## 部署到 Fly.io

仓库会构建成一个 Docker 镜像。FastAPI 会托管编译后的 React 前端，因此线上前后端同源，不需要单独部署前端。

```bash
fly launch --no-deploy
fly volumes create data --size 1 --region nrt

# 基础必填
fly secrets set ENV="production"
fly secrets set SECRET_KEY="replace-with-a-long-random-string"
fly secrets set APP_BASE_URL="https://tsfinancialsystem.fly.dev"

# BYOK 加密密钥（必填）
fly secrets set APP_ENCRYPTION_KEY="<生成的-fernet-key>" ALLOW_SYSTEM_AI_FALLBACK="false"

# 系统全局 AI Key（仅 ALLOW_SYSTEM_AI_FALLBACK=true 时生效，或站长自用）
fly secrets set DEEPSEEK_API_KEY="your-deepseek-api-key" AI_PROVIDER="deepseek"

# 邮件服务（可选；未配置时验证链接打印到 fly logs）
fly secrets set EMAIL_ENABLED="true"
fly secrets set EMAIL_FROM="noreply@yourdomain.com"
fly secrets set SMTP_HOST="smtp.example.com"
fly secrets set SMTP_PORT="587"
fly secrets set SMTP_USERNAME="your-smtp-user"
fly secrets set SMTP_PASSWORD="your-smtp-password"

fly deploy
```

本地 `.env` 不会上传到 Fly.io。生产环境密钥必须通过 `fly secrets set` 设置。

## 项目结构

```text
FinancialSystem/
├─ backend/
│  ├─ main.py                  FastAPI 入口和静态前端托管
│  ├─ models.py                SQLModel 表、schema 和资产计算逻辑
│  ├─ database.py              数据库引擎、初始化和轻量迁移
│  ├─ position.py              交易流水重放和 derived 持仓状态
│  ├─ price_provider.py        行情数据源
│  ├─ fx_provider.py           USD/CNY 汇率数据源
│  ├─ ai_client.py             GPT、DeepSeek、GLM、Claude 客户端抽象
│  └─ routers/                 API 路由模块
├─ frontend/
│  └─ src/
│     ├─ App.jsx               布局和路由
│     ├─ api/index.js          Axios API 层
│     └─ pages/                总览、平台、流水、投研、笔记等页面
├─ Dockerfile                  Docker 多阶段构建
├─ fly.toml                    Fly.io 部署配置
├─ dev.py                      跨平台开发启动器
└─ dashboard.png               项目截图
```

## 路线图

- [x] 多用户登录鉴权
- [x] Docker 和 Fly.io 部署
- [x] 交易流水驱动持仓
- [x] 投资笔记
- [x] 备份和恢复
- [x] 隐私模式和深色主题
- [x] AI 辅助投研工作台
- [x] 汇率缓存刷新
- [x] 邮箱验证、找回密码、旧 token 失效、进程内限流
- [x] 注册邮箱可选、安全问题找回密码、个人资料中支持设置安全问题
- [ ] 定时自动刷新行情
- [ ] PostgreSQL 部署选项
- [ ] 富途、盈透等券商 API 同步
- [ ] PWA 和移动端体验优化

## 免责声明

本项目用于个人资产记录和投研日志管理。行情数据和 AI 生成内容可能延迟、不完整或存在错误，不构成任何投资建议。

## License

Released under the [MIT License](LICENSE).

