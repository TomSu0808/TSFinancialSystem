<div align="center">

# 个人资产管理平台 · Personal Asset Manager

**A self-hosted, multi-currency portfolio tracker for stocks, funds, bonds, crypto & cash.**
按平台与币种统一管理多类资产，实时行情与汇率、总资产与盈亏一目了然。

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.128-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-5-646CFF?logo=vite&logoColor=white)](https://vitejs.dev/)
[![Ant Design](https://img.shields.io/badge/Ant%20Design-5-0170FE?logo=antdesign&logoColor=white)](https://ant.design/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)](./Dockerfile)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](#-license)

</div>

---

## 📖 Overview · 项目简介

A lightweight, **privacy-first** portfolio manager you run yourself. Organize holdings by
**platform** (Futu, IBKR, …) and **currency** (CNY / USD / HKD), pull live quotes and FX
rates on demand, and see total net worth, daily change, and cumulative P&L at a glance.

一个轻量、**数据自持**的资产管理平台：按**平台**（富途 / 盈透等）+ **币种**（人民币 / 美元 / 港币）
管理股票、基金、债券、加密、现金等资产，一键刷新行情与汇率，实时查看总资产、今日涨跌与累计盈亏。

> **Decoupled frontend & backend**, containerized, and ready to deploy to any cloud —
> access from your phone or computer over HTTPS.
> 前后端分离 + 容器化，可一键上云，手机 / 电脑随时随地访问。

---

## ✨ Features · 功能特性

| | Feature | 说明 |
|---|---|---|
| 📊 | **Unified dashboard** | 总览：总资产、今日涨跌、累计盈亏，¥/$ 一键切换 |
| 🏦 | **Platform & holdings management** | 按平台分组管理持仓，查看各平台市值与仓位占比 |
| 📈 | **Live quotes & FX** | A 股 / 港股 / 美股 / 基金 / 加密实时行情 + USD·CNY 汇率，手动刷新最可控 |
| 💹 | **P&L & net-worth trend** | 基于成本价的累计盈亏，每日净值快照绘制资产走势曲线 |
| 🥧 | **Allocation insights** | 按资产类型与平台的配置占比饼图 |
| 🧾 | **Transaction ledger** | 独立流水账（买入 / 卖出 / 分红 / 入金 / 出金） |
| 🔐 | **Multi-user auth** | JWT 登录，数据按用户隔离，密钥与配置全走环境变量 |
| 🕶️ | **Privacy & dark mode** | 一键打码所有金额（截图 / 公共场合）、深色主题 |
| 💾 | **Backup & restore** | 整账 JSON 导出 / 导入，方便迁移与备份 |
| 📱 | **Responsive & PWA-ready** | 同一局域网手机直接访问，上云后公网可用 |

---

## 🧱 Tech Stack · 技术栈

| Layer | Stack |
|---|---|
| **Backend** | FastAPI · SQLModel · SQLite · [akshare](https://github.com/akfamily/akshare) · python-jose (JWT) · bcrypt |
| **Frontend** | React 18 · Vite · Ant Design 5 · ECharts · React Router · Axios |
| **Infra** | Docker (multi-stage) · Fly.io · persistent volume |

---

## 🚀 Quick Start · 本地启动

**Prerequisites · 前置要求**：Python 3.10+、Node.js 18+

```bash
# Clone
git clone https://github.com/TomSu0808/TSFinancialSystem.git
cd TSFinancialSystem

# One command — auto-creates venv, installs deps, starts both servers
# 一键启动：自动建虚拟环境、装依赖、起前后端并打开浏览器
python3 dev.py start        # macOS / Linux  (Windows: 双击 start.bat)
```

| Service | URL |
|---|---|
| Frontend / 前端 | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |

Stop with `Ctrl+C`, or run `python3 dev.py stop`.
首次打开请先注册账号；同一 Wi-Fi 下用前端日志里的 `Network` 地址即可手机访问。

<details>
<summary>Manual setup · 手动分步启动</summary>

```bash
# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload          # http://localhost:8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev                        # http://localhost:5173
```
</details>

---

## ☁️ Deployment · 部署上云

The app ships as a **single Docker image**: the React build is served by FastAPI, so
frontend and backend are same-origin (no CORS), and SQLite lives on a **persistent volume**.

整个应用打包为**单个 Docker 镜像**：FastAPI 同源托管前端构建产物，SQLite 数据落在**持久卷**上，
重新部署不丢数据。以 [Fly.io](https://fly.io) 为例：

```bash
fly launch --no-deploy                       # 读取仓库内的 fly.toml
fly volumes create data --size 1 --region nrt  # 持久卷（与 app 同地区）
fly secrets set SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
fly deploy
```

Configuration via environment variables · 环境变量配置（见 [`backend/.env.example`](backend/.env.example)）：

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | random | JWT signing key — **set a fixed value in production** |
| `ACCESS_TOKEN_EXPIRE_DAYS` | `7` | Login validity (days) |
| `CORS_ORIGINS` | `*` | Allowed origins (tighten in production) |
| `ALLOW_REGISTRATION` | `true` | Toggle self-service signup |
| `DATA_DIR` | — | Directory for SQLite file (point to a mounted volume) |
| `DATABASE_URL` | — | Full DB URL — set to switch from SQLite to PostgreSQL |

---

## 🗂️ Project Structure · 工程结构

```
FinancialSystem/
├─ backend/                 FastAPI backend
│  ├─ main.py               Entry: DB init, routers, static frontend hosting
│  ├─ models.py             ★ Tables + schemas + market-value / P&L logic
│  ├─ database.py           Engine, init_db, lightweight migrations
│  ├─ price_provider.py     Quotes (akshare / CoinGecko)
│  ├─ fx_provider.py        FX rates (open.er-api.com, BOC fallback)
│  └─ routers/              platforms · holdings · fx · summary · …
├─ frontend/                React + Vite SPA
│  └─ src/                  pages/ · api/index.js (single API layer) · constants.js
├─ Dockerfile              Multi-stage build (Node → Python)
├─ fly.toml                Fly.io config + persistent volume
└─ dev.py                  Cross-platform dev launcher (start / stop / setup)
```

> 详细架构与数据流见 [ARCHITECTURE.md](ARCHITECTURE.md)，迭代记录见 [CHANGELOG.md](CHANGELOG.md)。

---

## 📡 Data Sources · 数据源

| Asset type | Source | Notes |
|---|---|---|
| A-share / HK / US / on-market funds | akshare (Eastmoney snapshot) | Free, no API key; ~15 min delay |
| Off-market funds | akshare fund NAV | Latest unit NAV by fund code |
| Crypto | CoinGecko (free API) | BTC / ETH / … or a CoinGecko id |
| USD·CNY FX | open.er-api.com | Falls back to Bank of China rate |

Quotes refresh **on demand** (manual "Update" button) — minimal API calls, full control.

---

## 🗺️ Roadmap · 路线图

- [x] Multi-user auth (JWT) · 多用户登录
- [x] Cloud deployment (Docker + Fly.io) · 容器化上云
- [ ] Scheduled auto-refresh (APScheduler) · 定时自动刷新行情
- [ ] PostgreSQL option for scale · 切换 PostgreSQL
- [ ] Broker API sync (Futu / IBKR) · 券商 API 直连同步持仓
- [ ] PWA / mobile polish · 移动端 PWA 优化

---

## 📄 License

Released under the [MIT License](LICENSE).

---

<div align="center">
<sub>Built with FastAPI · React · akshare</sub>
</div>
