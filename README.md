# TSFinancialSystem

<div align="center">

**A self-hosted portfolio management and AI investment research platform for multi-currency personal assets.**

[Live Site](https://tsfinancialsystem.fly.dev/) | [中文](README.zh-CN.md) | [Architecture](ARCHITECTURE.md) | [Technical Roadmap](TECHNICAL_ROADMAP.md) | [Changelog](CHANGELOG.md)

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.128-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-5-646CFF?logo=vite&logoColor=white)](https://vitejs.dev/)
[![Ant Design](https://img.shields.io/badge/Ant%20Design-5-0170FE?logo=antdesign&logoColor=white)](https://ant.design/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)](Dockerfile)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

## What It Is

TSFinancialSystem helps individual investors manage stocks, funds, bonds, crypto, and cash in one private web app. It organizes assets by account, asset type, and currency, then connects transactions, holdings, market data, FX rates, portfolio analytics, decision logs, and AI research reports into one workflow.

It is not just a bookkeeping app. It is a personal investment workspace for people who want to own their portfolio data, understand their positions, and keep research decisions traceable.

## Who It Is For

- Individual investors with multiple brokers, bank accounts, wallets, or fund accounts.
- People who hold assets across CNY, USD, HKD, and other currencies.
- Users who want transactions to drive holdings, cost basis, and realized P&L.
- Long-term investors who want AI research, action items, and reviews in one place.
- Self-hosting users who prefer to control their own portfolio data.

## Live Demo

Visit: <https://tsfinancialsystem.fly.dev/>

The hosted version supports registration, login, HTTPS, and isolated multi-user data. Do not enter real sensitive portfolio data in a public demo environment.

## Core Capabilities

| Capability | What it does |
| --- | --- |
| Multi-account tracking | Manage assets by broker, bank, wallet, or custom account, such as Futu, IBKR, Tiger, bank cards, and crypto wallets. |
| Multi-currency overview | Track CNY, USD, HKD, and more, with a global CNY / USD display-currency switch. |
| Transaction-driven holdings | Buy, sell, and dividend transactions update derived holdings, weighted-average cost, realized P&L, and closed-position status. |
| Dashboard | Review total assets, daily change, total return, unrealized / realized P&L, allocation, net-worth charts, and data status. |
| Market and FX refresh | Refresh A-share, HK, US, fund, crypto, and USD/CNY FX data through free data sources. |
| CSV import and reconciliation | Import Futu, IBKR, or generic CSV files with preview validation, deduplication, commit, and reconciliation. |
| Cash ledger | Deposit and withdraw records maintain derived cash holdings per account and currency. |
| Decision log | Track thesis, risk, review, action items, and observations, linked to symbols or holdings. |
| AI research workspace | Generate Chinese or English research reports with GPT, DeepSeek, GLM, Claude, or other OpenAI-compatible providers. |
| AI action loop | Extract action items from AI reports into the decision log and track their status over time. |
| Alerts | Create rules for price thresholds, daily change, allocation, stale data, and refresh failures. |
| Privacy and security | JWT auth, per-user isolation, amount masking, dark mode, email verification, password recovery, and BYOK. |
| Self-hosting | One Docker image serves the React frontend and FastAPI backend. SQLite is the default, with PostgreSQL available through `DATABASE_URL`. |

## Typical Workflow

1. Register an account and create platforms for brokers, banks, wallets, or custom accounts.
2. Add manual holdings, or record buy, sell, dividend, deposit, and withdraw transactions.
3. Import historical transactions with CSV when migrating existing records.
4. Refresh market prices and FX rates, or enable scheduled refresh on the Dashboard.
5. Review total assets, returns, allocation, net-worth trend, and data freshness.
6. Generate AI research for important holdings and save action items into the decision log.
7. Export a full-account JSON backup when you need to migrate or archive data.

## Page Overview

| Page | Purpose |
| --- | --- |
| Dashboard | Total assets, daily P&L, return breakdown, allocation, net-worth chart, data status, and refresh controls. |
| Platforms | Organize assets by broker, bank, wallet, or custom account. |
| Holding detail | Manage manual assets and inspect derived holdings, cost, P&L, and research summaries. |
| Transactions | Record, search, filter, and import buy / sell / dividend / deposit / withdraw records. |
| AI Research | Select a template, choose a symbol or portfolio, and generate structured Markdown reports. |
| Decision Log | Track thesis, risks, reviews, action items, and links to holdings or AI reports. |
| Alerts | Manage alert rules and review triggered events or refresh failures. |

## Data Sources

| Data | Source | Notes |
| --- | --- | --- |
| A-share, HK, US stocks, on-market funds | akshare / Eastmoney snapshots | Free sources, may be delayed or incomplete. |
| Off-market funds | akshare fund NAV | Latest NAV by fund code. |
| Crypto | CoinGecko Free API | Supports common symbols and CoinGecko IDs. |
| USD/CNY FX | open.er-api.com, with Bank of China fallback | Used for CNY / USD display conversion. |
| AI reports | User-configured AI provider | BYOK supported. AI output is not investment advice. |

## Quick Start

Prerequisites:

- Python 3.10+
- Node.js 18+

```bash
git clone https://github.com/TomSu0808/TSFinancialSystem.git
cd TSFinancialSystem
python dev.py start
```

`python dev.py start` prepares the local environment, starts the FastAPI backend, starts the Vite frontend, and opens the browser.

| Service | URL |
| --- | --- |
| Frontend | <http://localhost:5173> |
| Backend API | <http://localhost:8000> |
| API docs | <http://localhost:8000/docs> |

Stop the local services:

```bash
python dev.py stop
```

Install dependencies without starting the app:

```bash
python dev.py setup
```

## Configuration

For local development, copy `backend/.env.example` to `backend/.env`. In production, store secrets through your deployment platform.

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | JWT signing key. Use a stable random value in production. |
| `ENV` | Set to `production` to enable production startup checks. |
| `DATA_DIR` | SQLite data directory, such as `/data` on Fly.io. |
| `DATABASE_URL` | Optional database connection URL. PostgreSQL is used when set; otherwise SQLite is used. |
| `ALLOW_REGISTRATION` | Enables or disables public registration. Defaults to `true`. |
| `APP_BASE_URL` | Public URL used for email verification and password-reset links. |
| `APP_ENCRYPTION_KEY` | Required in production to encrypt user AI API keys. |
| `ALLOW_SYSTEM_AI_FALLBACK` | Allows fallback to a system-level AI key when a user has no key. Defaults to `false`. |
| `AI_PROVIDER` | Default AI provider, such as `gpt`, `deepseek`, `glm`, or `claude`. |
| `EMAIL_ENABLED` | Enables SMTP email. When disabled, verification links are printed to logs. |
| `AUTO_REFRESH_ENABLED` | Enables scheduled refresh. |
| `AUTO_REFRESH_TIME` | Daily refresh time in `HH:MM` format. |
| `AUTO_REFRESH_TIMEZONE` | Timezone for scheduled refresh. Defaults to `Asia/Shanghai`. |
| `ALERTS_ENABLED` | Enables alert rule evaluation. |

## PostgreSQL Deployment

SQLite is the default and works well for personal use. For multi-user production use or managed backups, set `DATABASE_URL` to switch to PostgreSQL.

```bash
fly secrets set DATABASE_URL="postgresql+psycopg2://user:password@your-pg-host:5432/dbname"
```

When `DATABASE_URL` is set, SQLite `DATA_DIR` is ignored and the app creates the required tables on first startup.

## Deploy to Fly.io

The Docker image builds the React frontend first, then FastAPI serves both the frontend static files and backend API from the same origin.

```bash
fly launch --no-deploy
fly volumes create data --size 1 --region nrt

fly secrets set ENV="production"
fly secrets set SECRET_KEY="replace-with-a-long-random-string"
fly secrets set APP_BASE_URL="https://your-app.fly.dev"
fly secrets set APP_ENCRYPTION_KEY="<your-fernet-key>" ALLOW_SYSTEM_AI_FALLBACK="false"

fly deploy
```

For real email delivery, also configure `EMAIL_ENABLED`, `EMAIL_FROM`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, and `SMTP_PASSWORD`.

## Tech Stack

| Layer | Stack |
| --- | --- |
| Backend | FastAPI, SQLModel, SQLite, PostgreSQL, JWT, akshare, CoinGecko, OpenAI-compatible AI clients |
| Frontend | React 18, Vite, Ant Design 5, ECharts, React Router, Axios, react-markdown, remark-gfm |
| Deployment | Docker multi-stage build, Fly.io, persistent volume |
| Testing | Pytest, HTTPX, frontend build checks |

## Repository Map

```text
FinancialSystem/
├── backend/                    FastAPI backend
│   ├── main.py                 App entrypoint, route mounting, static frontend hosting
│   ├── models.py               SQLModel tables, API schemas, and portfolio calculations
│   ├── database.py             Database connection, initialization, and lightweight migrations
│   ├── position.py             Transaction replay and derived holding calculation
│   ├── import_service.py       CSV import preview, commit, and deduplication
│   ├── reconciliation_service.py
│   ├── importers/              Futu, IBKR, and generic import parsers
│   ├── routers/                API route modules
│   └── tests/                  Backend tests
├── frontend/                   React frontend
│   └── src/
│       ├── api/                Axios API layer
│       ├── pages/              Dashboard, platforms, transactions, AI, logs, alerts
│       ├── displaySettings.jsx Global display-currency context
│       └── colorScheme.jsx     Up/down color preference
├── docs/                       Design documents and historical plans
├── Dockerfile                  Combined frontend/backend image
├── fly.toml                    Fly.io deployment configuration
├── dev.py                      Cross-platform development launcher
└── TECHNICAL_ROADMAP.md        Technical roadmap
```

## Documentation

- [Architecture](ARCHITECTURE.md): project structure, core data models, APIs, and key data flows.
- [Technical Roadmap](TECHNICAL_ROADMAP.md): engineering roadmap, priorities, and acceptance criteria.
- [Changelog](CHANGELOG.md): completed features and behavior changes.
- [Phase 1 Import Design](docs/superpowers/specs/2026-06-28-phase1-import-reconciliation-design.md): import and reconciliation system design.

## Disclaimer

This project is for personal asset tracking, investment research logging, and engineering learning. Market data, FX data, and AI-generated content may be delayed, incomplete, or wrong. Nothing in this project is financial advice.

## License

Released under the [MIT License](LICENSE).
