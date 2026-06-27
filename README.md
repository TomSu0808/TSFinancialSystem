<div align="center">

# TSFinancialSystem

**A self-hosted portfolio and investment research system for multi-currency personal assets.**

[Live Site](https://tsfinancialsystem.fly.dev/) ·
[中文](README.zh-CN.md) ·
[Architecture](ARCHITECTURE.md) ·
[Changelog](CHANGELOG.md)

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.128-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-5-646CFF?logo=vite&logoColor=white)](https://vitejs.dev/)
[![Ant Design](https://img.shields.io/badge/Ant%20Design-5-0170FE?logo=antdesign&logoColor=white)](https://ant.design/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)](Dockerfile)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

## What It Does

TSFinancialSystem helps you track stocks, funds, bonds, crypto, cash, and investment notes in one private web app. Assets are organized by platform and currency, with live quotes, USD/CNY exchange rates, transaction-driven holdings, net-worth charts, allocation views, and AI-assisted research reports.

It is designed for people who want a clear personal finance cockpit without handing their portfolio data to a third-party SaaS platform.

## Live Site

The project is deployed at:

**https://tsfinancialsystem.fly.dev/**

The app supports account registration, login, multi-user data isolation, and HTTPS access through Fly.io.

## Highlights

| Area | What you get |
|---|---|
| Portfolio dashboard | Total assets, daily change, total return, realized/unrealized P&L, dividend income, and net-worth history |
| Multi-currency assets | CNY, USD, and HKD holdings with USD/CNY exchange-rate conversion |
| Platform-based tracking | Group assets by brokerage or account, such as Futu, IBKR, Tiger, banks, wallets, or custom platforms |
| Live market data | A-share, HK, US, fund, crypto, and FX data through free data sources |
| Transaction-driven holdings | Buy/sell/dividend records automatically update quantity, weighted-average cost, realized P&L, and closed positions |
| Manual assets | Track cash, bonds, private funds, or assets without quote APIs through manually entered market value |
| Investment journal | Write and manage notes for investment decisions, reviews, and thesis tracking |
| AI research workspace | Generate research prompts and reports with GPT, DeepSeek, GLM, or Claude-compatible providers |
| Privacy tools | User authentication, data isolation, amount masking, dark mode, backup, and restore |
| Self-hosted deployment | One Docker image serves both React and FastAPI, with SQLite persisted on a Fly.io volume |

## Product Flow

1. Create platforms for your accounts, brokers, or wallets.
2. Add manual holdings or create transaction records.
3. Refresh quotes and exchange rates on demand.
4. Review total assets, returns, allocation, and net-worth trend.
5. Keep investment notes and generate AI-assisted research reports.
6. Export a full-account JSON backup when needed.

## Tech Stack

| Layer | Stack |
|---|---|
| Backend | FastAPI, SQLModel, SQLite, JWT auth, akshare, CoinGecko, OpenAI-compatible AI clients |
| Frontend | React 18, Vite, Ant Design 5, ECharts, React Router, Axios |
| Infrastructure | Docker multi-stage build, Fly.io, persistent volume |
| Data | SQLite by default, optional database URL support for future migration |

## Data Sources

| Data | Source | Notes |
|---|---|---|
| A-share, HK, US stocks, on-market funds | akshare / Eastmoney snapshots | Free data, usually delayed |
| Off-market funds | akshare fund NAV | Latest available NAV by fund code |
| Crypto | CoinGecko free API | Supports common symbols and CoinGecko IDs |
| USD/CNY FX | open.er-api.com | Falls back to Bank of China data |

## Local Development

Prerequisites:

- Python 3.10+
- Node.js 18+

```bash
git clone https://github.com/TomSu0808/TSFinancialSystem.git
cd TSFinancialSystem
python dev.py start
```

The launcher creates the backend virtual environment, installs dependencies, starts FastAPI and Vite, and opens the app.

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |

Stop the dev servers:

```bash
python dev.py stop
```

Manual startup:

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

## Configuration

For local development, copy `backend/.env.example` to `backend/.env`.

Important variables:

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | JWT signing key. Must be set to a stable random value in production |
| `ENV` | `production` enables startup config checks (exits if required vars are missing) |
| `DATA_DIR` | Directory for the SQLite database, such as `/data` on Fly.io |
| `DATABASE_URL` | Optional full database URL |
| `ALLOW_REGISTRATION` | Enable or disable public registration (default `true`) |
| `APP_BASE_URL` | Public URL used for email verification and password-reset links. Required in production |
| `EMAIL_ENABLED` | `false` (default) prints verification links to the console; `true` sends real email via SMTP. Only needed if users set an email address |
| `EMAIL_FROM` | Sender address for outgoing emails |
| `SMTP_HOST` | SMTP server hostname |
| `SMTP_PORT` | SMTP port. Default: 587 |
| `SMTP_USERNAME` | SMTP username |
| `SMTP_PASSWORD` | SMTP password |
| `SMTP_TLS` | `true` for SSL/TLS; `false` for STARTTLS. Default: `true` |
| `AI_PROVIDER` | Default AI provider: `gpt`, `deepseek`, `glm`, or `claude` |
| `DEEPSEEK_API_KEY` | Required when using DeepSeek |
| `OPENAI_API_KEY` | Required when using GPT/OpenAI |
| `GLM_API_KEY` | Required when using GLM |
| `ANTHROPIC_API_KEY` | Required when using Claude |
| `FX_REFRESH_INTERVAL_SECONDS` | USD/CNY cache TTL. Default: 21600 seconds |

## Deploy To Fly.io

This repository builds into one Docker image. FastAPI serves the compiled React app, so the deployed app is same-origin and does not need a separate frontend host.

```bash
fly launch --no-deploy
fly volumes create data --size 1 --region nrt

# Required
fly secrets set ENV="production"
fly secrets set SECRET_KEY="replace-with-a-long-random-string"
fly secrets set APP_BASE_URL="https://tsfinancialsystem.fly.dev"

# AI research (set whichever provider you use)
fly secrets set DEEPSEEK_API_KEY="your-deepseek-api-key" AI_PROVIDER="deepseek"

# Email (optional; if not set, verification links are printed to fly logs)
fly secrets set EMAIL_ENABLED="true"
fly secrets set EMAIL_FROM="noreply@yourdomain.com"
fly secrets set SMTP_HOST="smtp.example.com"
fly secrets set SMTP_PORT="587"
fly secrets set SMTP_USERNAME="your-smtp-user"
fly secrets set SMTP_PASSWORD="your-smtp-password"

fly deploy
```

Local `.env` files are not uploaded to Fly.io. Production keys must be set with `fly secrets set`.

## Repository Map

```text
FinancialSystem/
├─ backend/
│  ├─ main.py                  FastAPI entrypoint and static frontend hosting
│  ├─ models.py                SQLModel tables, schemas, and portfolio math
│  ├─ database.py              Engine, DB init, and lightweight migrations
│  ├─ position.py              Transaction replay and derived holding state
│  ├─ price_provider.py        Quote providers
│  ├─ fx_provider.py           USD/CNY exchange-rate providers
│  ├─ ai_client.py             GPT, DeepSeek, GLM, and Claude client abstraction
│  └─ routers/                 API route modules
├─ frontend/
│  └─ src/
│     ├─ App.jsx               Layout and routing
│     ├─ api/index.js          Axios API layer
│     └─ pages/                Dashboard, platforms, transactions, research, notes
├─ Dockerfile                  Multi-stage Docker build
├─ fly.toml                    Fly.io deployment config
├─ dev.py                      Cross-platform dev launcher
└─ dashboard.png               Project screenshot
```

## Roadmap

- [x] Multi-user authentication
- [x] Docker and Fly.io deployment
- [x] Transaction-driven holdings
- [x] Investment journal
- [x] Backup and restore
- [x] Privacy mode and dark theme
- [x] AI-assisted research workspace
- [x] Exchange-rate cache refresh
- [x] Email verification, forgot/reset password, JWT invalidation on password change, in-process rate limiting
- [x] Optional email registration, security-question password recovery, security question in profile settings
- [ ] Scheduled quote refresh
- [ ] PostgreSQL deployment option
- [ ] Broker API sync for Futu, IBKR, and other providers
- [ ] PWA/mobile polish

## Disclaimer

This project is for personal asset tracking and research logging. Market data and AI-generated content may be delayed, incomplete, or incorrect. Nothing in this project is financial advice.

## License

Released under the [MIT License](LICENSE).

