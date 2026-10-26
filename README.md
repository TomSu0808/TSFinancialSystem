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
| Multi-currency overview | Track CNY, USD, HKD, and more; switch between CNY / USD on the Dashboard, account list, and account detail, with a saved display preference. |
| Transaction-driven holdings | Buy, sell, and dividend transactions update derived holdings, weighted-average cost, realized P&L, and closed-position status. |
| Dashboard | Review total assets, daily change, total return, unrealized / realized P&L, allocation, net-worth charts, and data status. Daily P&L uses per-position prior-day baselines, so a new or unpriceable holding does not invalidate otherwise comparable positions. |
| Market and FX refresh | Refresh A-share, HK, US, fund, crypto, and USD/CNY FX data; creating, editing, deleting, or importing transactions automatically refreshes market quotes. |
| CSV import and reconciliation | Import Futu, IBKR, or generic CSV files with preview validation, deduplication, commit, and reconciliation. |
| Cash ledger | Track cash per account and currency; net sale proceeds remain in the account, while withdrawals reduce cash separately. Includes calibration, ledger history, and overdraft checks. |
| Mobile workflows | Five-tab bottom navigation, holding/cash/transaction cards, expandable details, transaction pagination, collapsed filters, and stacked entry forms. |
| Decision log | Track thesis, risk, review, action items, and observations, linked to symbols or holdings. |
| AI research workspace | Four task entries (company / earnings / portfolio / thesis) with every AI Berkshire template still available; preview the exact data sent before submitting. Supports GPT, DeepSeek, GLM, Claude, and other OpenAI-compatible providers. |
| Structured reports and follow-ups | Each report opens with a structured summary (conclusion, sourced facts, risks, impact, next watch) and labels facts, analysis, and assumptions separately. Ask follow-up questions inside a report; answers are stored separately and never overwrite it. |
| Research and tracking loop | "Update this research" creates a new version with a preserved version chain, and tracking items are previewed, selected, and saved into the decision log. Missing dates are never invented. |
| Multi-agent collaboration | The investment-committee template can run a pinned TradingAgents workflow in an isolated worker subprocess: social disabled by default, one research and one risk round, no asset write access, per-account memory and cache isolation. |
| Privacy and security | JWT auth, per-user isolation, amount masking, dark mode, email verification, password recovery, and BYOK. |
| Self-hosting | One Docker image serves the React frontend and FastAPI backend. SQLite is the default, with PostgreSQL available through `DATABASE_URL`. |

## Typical Workflow

1. Register an account and create platforms for brokers, banks, wallets, or custom accounts.
2. Add manual holdings, or record buy, sell, dividend, deposit, withdraw, and cash-adjustment transactions.
3. Import historical transactions with CSV when migrating existing records.
4. Quotes refresh after transaction changes; use the Dashboard refresh button to update FX or retry unavailable quotes.
5. Review total assets, returns, allocation, net-worth trend, and data freshness.
6. Generate research from the AI Research task entries and expand "review this input" before submitting.
7. Read the structured summary, ask follow-up questions in the report, or run "Update this research" to verify new material.
8. Preview and select tracking items to save into the decision log.
9. Export a full-account JSON backup when you need to migrate or archive data.


## Page Overview

| Page | Purpose |
| --- | --- |
| Dashboard | Total assets, daily P&L, return breakdown, allocation, net-worth chart, data status, and refresh controls. |
| Platforms | Organize assets by broker, bank, wallet, or custom account. |
| Holding detail | Manage manual assets and inspect derived holdings, cost, P&L, research summaries, and per-currency cash accounts. |
| Transactions | Record, search, filter, and import buy / sell / dividend / deposit / withdraw / cash-adjustment records; the buy/sell form shows current holdings and cash impact. |
| AI Research | Task-first research for a company, earnings, portfolio, or thesis; input preview, structured summaries, report follow-ups, versioned updates, and tracking items. The investment-committee template can run a pinned TradingAgents multi-agent workflow. |
| Decision Log | Track thesis, risks, reviews, action items, and links to holdings or AI reports. |

## Sales, Cash, and Withdrawals

Account assets include holdings at market value and cash. Net sale proceeds (quantity × price minus fees, or the entered net amount) stay in the same account and currency for reinvestment. Record a withdrawal only when money leaves the account. A $1,000 sale with $5 fees adds $995 cash; a subsequent $300 withdrawal reduces cash by $300.

The first sale starts cash tracking automatically. Use cash calibration in account detail to record existing idle cash as an absolute balance at that date. Historical purchases before cash tracking starts do not infer missing deposits; later purchases deduct cash. Calibration replaces the previous running balance rather than adding it twice.

Edits, deletions, and imports recalculate holdings and cash. Failed quote refreshes keep the saved transaction and display the last available price. Upgrades rebuild historical sale cash; existing gaps can be repaired, while new or worsened overdrafts are rejected.

## Mobile Use

The bottom navigation opens overview, accounts, transactions, research, and notes. Holding, cash-ledger, and transaction cards expand to reveal costs, fees, notes, and actions. Transaction filters start collapsed, records paginate in groups of 20, and entry forms stack vertically. Display-currency changes preserve the original transaction currency.

Price/allocation alerts were removed on 2026-10-09, including their pages, APIs, and evaluation jobs. Scheduled market and FX refreshes continue to run.

## Data Sources

| Data | Source | Notes |
| --- | --- | --- |
| A-share, HK, US stocks, on-market funds | akshare / Eastmoney snapshots | Free sources, may be delayed or incomplete. |
| Off-market funds | akshare fund NAV | Latest NAV by fund code. |
| Crypto | CoinGecko Free API | Supports common symbols and CoinGecko IDs. |
| USD/CNY FX | open.er-api.com, with Bank of China fallback | Used for CNY / USD display conversion. |
| AI reports | User-configured AI provider | BYOK supported. AI output is not investment advice. |

## AI Research v2 and TradingAgents

Research starts from a task instead of a template list; every AI Berkshire template remains under "All research tools":

- **Research a company** (deep company research), **Review earnings** (earnings review), **Check my portfolio** (portfolio review), and **Revisit the thesis** (thesis tracker).
- Opening research from a holding pre-fills the target. Ambiguous name, symbol, or market requires an explicit holding choice; the system never guesses.
- Before submitting, expand the input preview to see the exact holdings, cost, cash, prior research, notes, and data cutoff included. Personal holding context can be turned off.
- The report opens with the conclusion, sourced key facts, risks, impact on your holding or objective, and next watch items. Facts, analysis, and assumptions are labeled separately, and sources are never marked "verified".
- Follow-up questions live inside the report; the first question automatically carries the saved report and its input snapshot, and answers never overwrite the report. Search is off by default; when enabled, any newly retrieved sources and their retrieval time are listed.
- "Update this research" creates a new version from the old report as a baseline and keeps the version chain. When no new material was retrieved, the report says so instead of just changing the date.
- Tracking items reuse the decision log: candidates are previewed, then selected and saved by the user, with optional metric, review date, and event condition.
- Standard and multi-agent runs both execute in the background: submission returns immediately and the UI polls real events, so no manual refresh is needed.

**Investment-committee multi-agent**: only the `investment-team` template offers "multi-agent collaboration", which calls a pinned commit of [TradingAgents](https://github.com/TauricResearch/TradingAgents) (`e8f5503e9b86d5c2710b0c76b1f686703968c9df`). Analysts default to fundamentals, market, and institutional news (social disabled), with one research-debate and one risk-debate round; the strategy node returns research views and scenarios only. The worker runs in its own subprocess, has no asset database access, and isolates memory, cache, and checkpoints per account.

**Cost and budget**: usage comes from each provider's raw usage, cached tokens are not double-counted, and cost is only calculated when `AI_PRICE_TABLE_JSON` covers the model and usage is complete. Otherwise it is shown as unknown. Per-run call, output-token, time, and cost limits stop further steps; cancellation terminates the worker or calls the provider cancel API.

See [docs/ai-research-and-tradingagents.md](docs/ai-research-and-tradingagents.md) for configuration, migration, APIs, rollback, and verification limits.

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
| `RESEARCH_MAX_LLM_CALLS` | Per-run model call limit; defaults to 12 for standard and 60 for multi-agent. |
| `RESEARCH_MAX_OUTPUT_TOKENS` | Per-run output token limit; defaults to 120000. |
| `RESEARCH_MAX_SECONDS` | Per-run time limit; defaults to 1800s standard and 3600s multi-agent. |
| `RESEARCH_MAX_BUDGET` | Optional per-run cost cap; requires a price table or the run is refused. |
| `AI_PRICE_TABLE_JSON` | Per-million-token prices by provider/model; cost is unknown when unset. |
| `TRADINGAGENTS_PYTHON` | Python 3.11+ environment with TradingAgents installed; Docker uses `/opt/tradingagents-venv/bin/python`. |
| `TRADINGAGENTS_DATA_ROOT` | Isolated directory for multi-agent memory, cache, checkpoints, and results. |
| `TRADINGAGENTS_MAX_TOOL_ROUNDS` | Tool-call rounds per analyst; defaults to 8. |

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

The Docker image installs the pinned TradingAgents release into its own virtualenv. Multi-agent runs use more memory, so on Fly.io:

```bash
fly scale memory 1024
```

If you do not use multi-agent, deploy with `fly deploy --build-arg INSTALL_TRADINGAGENTS=0` to skip the install and keep the image smaller. The UI then reports the engine as unavailable while standard research keeps working.

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
│       ├── pages/              Dashboard, platforms, transactions, AI, logs
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

## Development Checks

In a Python environment with backend dependencies installed, run `cd backend` and `python -m pytest tests/ -q`. For the frontend, run `cd frontend`, `npm ci`, `npm test`, and `npm run build`. GitHub Actions checks backend tests, frontend tests/build, and the Docker image build.

## Disclaimer

This project is for personal asset tracking, investment research logging, and engineering learning. Market data, FX data, and AI-generated content may be delayed, incomplete, or wrong. Nothing in this project is financial advice.

## License

Released under the [MIT License](LICENSE).
