# TSFinancialSystem

<div align="center">

**A self-hosted personal finance workspace for multi-account portfolios and AI-assisted investment research.**

[Live Demo](https://tsfinancialsystem.fly.dev/) · [中文文档](README.zh-CN.md) · [Architecture](ARCHITECTURE.md) · [Roadmap](TECHNICAL_ROADMAP.md) · [Changelog](CHANGELOG.md)

[![CI](https://github.com/TomSu0808/TSFinancialSystem/actions/workflows/ci.yml/badge.svg)](https://github.com/TomSu0808/TSFinancialSystem/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.128-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)](Dockerfile)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

TSFinancialSystem brings portfolio tracking, transaction-ledger accounting, market data, cash management, decision logs, and AI research into one private web application. It is designed for investors who want to understand their positions and keep control of their data.

> This project is for personal asset tracking, investment research logging, and engineering learning. It is not financial advice.

## What You Can Do

| Area | Capabilities |
| --- | --- |
| **Portfolio** | Manage brokers, banks, wallets, funds, stocks, bonds, crypto, cash, and multiple display currencies. |
| **Ledger** | Replay buy, sell, dividend, deposit, withdrawal, and cash-adjustment transactions into holdings, cost basis, realized P&L, and cash balances. |
| **Research** | Run company research, earnings reviews, portfolio reviews, and thesis tracking with GPT or DeepSeek. DeepSeek uses `deepseek-flash` (V4.1-Flash-1017). |
| **Review** | Save structured reports, sources, follow-up conversations, versioned updates, action items, and decision notes. |

## Why It Exists

| Without a private workspace | With TSFinancialSystem |
| --- | --- |
| Portfolio data is split across brokers, banks, and spreadsheets. | Accounts, holdings, cash, and transactions are organized in one workspace. |
| Positions and returns are recalculated manually. | Transaction replay derives holdings, cost basis, realized P&L, and cash movements. |
| Research is scattered across chats and notes. | Reports, sources, follow-ups, versions, and tracking items stay connected. |
| AI answers may rely on stale knowledge. | Optional web retrieval adds dated external search results to research prompts. |
| Portfolio data depends on a hosted product. | Deploy the application yourself with SQLite or PostgreSQL. |

## Features

### Portfolio and Ledger

- Multi-account asset tracking for brokers, banks, wallets, and custom platforms.
- CNY, USD, HKD, and other currency support with configurable display currency.
- Transaction-driven holdings, weighted-average cost, realized P&L, dividends, and closed positions.
- Cash ledger by account and currency, including sale proceeds, withdrawals, calibration, and overdraft checks.
- Market and FX refresh for A-shares, Hong Kong stocks, US stocks, funds, crypto, and USD/CNY.
- CSV import, preview validation, deduplication, commit, and reconciliation for Futu, IBKR, and generic files.

### AI Research

- Task-first entry points for company research, earnings review, portfolio review, and thesis tracking.
- GPT and DeepSeek provider support; DeepSeek defaults to `deepseek-flash`.
- Optional live retrieval: DeepSeek uses its Search API and GPT uses OpenAI web search.
- Structured reports that separate facts, analysis, assumptions, risks, and follow-up items.
- Follow-up questions stored independently from the original report.
- Versioned research updates with preserved report history and source timestamps.
- Optional pinned TradingAgents multi-agent workflow in an isolated worker process.

### Security and Deployment

- Self-hosted Docker deployment with FastAPI and React served from one image.
- SQLite by default; PostgreSQL through `DATABASE_URL`.
- JWT authentication, per-user data isolation, email verification, password recovery, and BYOK API keys.
- No API keys, account databases, or exported backups are required in the repository.

## Who It Is For

- Investors with multiple broker, bank, wallet, or fund accounts.
- People holding assets across CNY, USD, HKD, and other currencies.
- Users who want transaction records to drive portfolio calculations.
- Investors who want research and decision notes to remain traceable over time.
- Self-hosting users who prefer to control their portfolio data.

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+

### Run Locally

```bash
git clone https://github.com/TomSu0808/TSFinancialSystem.git
cd TSFinancialSystem
python dev.py start
```

The launcher prepares the backend environment, starts FastAPI and Vite, and opens the application in a browser.

| Service | URL |
| --- | --- |
| Frontend | <http://localhost:5173> |
| Backend API | <http://localhost:8000> |
| API docs | <http://localhost:8000/docs> |

Stop the local services:

```bash
python dev.py stop
```

Prepare dependencies without starting the application:

```bash
python dev.py setup
```

## Configure the Application

For local development, copy the example configuration:

```bash
cp backend/.env.example backend/.env
```

Keep secrets in `backend/.env` locally or in your deployment platform's secret store. Do not commit `.env`, `data.db`, account backups, or API keys.

Important settings:

| Variable | Purpose |
| --- | --- |
| `ENV` | Set to `production` to enable production startup checks. |
| `DATA_DIR` | SQLite data directory, such as `/data` on Fly.io. |
| `DATABASE_URL` | Optional PostgreSQL connection URL; SQLite is used when unset. |
| `ALLOW_REGISTRATION` | Enables public registration; defaults to `true`. |
| `APP_BASE_URL` | Public URL for email verification and password-reset links. |
| `APP_ENCRYPTION_KEY` | Required in production to encrypt user AI API keys. |
| `AI_PROVIDER` | Default provider: `gpt` or `deepseek`. |
| `DEEPSEEK_MODEL` | Defaults to `deepseek-flash`, the DeepSeek-V4.1-Flash-1017 API model. |
| `DEEPSEEK_SEARCH_ENABLED` | Enables DeepSeek Search API retrieval; defaults to `true`. |
| `RESEARCH_MAX_LLM_CALLS` | Per-run model-call limit; defaults to 12 for standard and 60 for multi-agent runs. |
| `RESEARCH_MAX_OUTPUT_TOKENS` | Per-run output-token limit; defaults to 120000. |
| `RESEARCH_MAX_SECONDS` | Per-run time limit; defaults to 1800 seconds for standard and 3600 seconds for multi-agent runs. |
| `AI_PRICE_TABLE_JSON` | Optional provider/model price table used for cost reporting and budget limits. |

See [`backend/.env.example`](backend/.env.example) for the complete configuration reference.

## AI Research and Fresh Data

When web retrieval is enabled, the system records the retrieval request, query results, dates, URLs, and retrieval time with the report. Sources are marked as fetched by the system, not as independently verified. A search request is not a substitute for checking the issuer's filings, exchange announcements, or regulatory disclosures.

DeepSeek retrieval uses the standalone Search API because the DeepSeek Responses API web-search tool is not available on `deepseek-flash`. Search requests are billed separately by DeepSeek. Disable `DEEPSEEK_SEARCH_ENABLED` when the feature is not needed.

The detailed research workflow, TradingAgents integration, budget controls, migration behavior, and verification limits are documented in [`docs/ai-research-and-tradingagents.md`](docs/ai-research-and-tradingagents.md).

## Fly.io Deployment

The repository includes [`fly.toml`](fly.toml) and a Dockerfile for a combined frontend/backend deployment.

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

For multi-agent research, allocate at least 1 GB memory:

```bash
fly scale memory 1024
```

If multi-agent research is not needed, skip the TradingAgents image layer:

```bash
fly deploy --build-arg INSTALL_TRADINGAGENTS=0
```

## Documentation

- [Architecture](ARCHITECTURE.md): project structure, data models, APIs, and data flow.
- [AI Research and TradingAgents](docs/ai-research-and-tradingagents.md): research workflow, live retrieval, multi-agent execution, configuration, and limits.
- [Technical Roadmap](TECHNICAL_ROADMAP.md): engineering priorities and acceptance criteria.
- [Changelog](CHANGELOG.md): shipped behavior changes.

## Development Checks

Backend:

```bash
cd backend
python -m pytest tests/ -q
```

Frontend:

```bash
cd frontend
npm ci
npm test
npm run build
```

GitHub Actions also checks backend tests, frontend tests/build, and the Docker image build.

## License

Released under the [MIT License](LICENSE).
