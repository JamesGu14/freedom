# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Freedom Quant Platform** - A Chinese A-stock daily-level quantitative research and backtesting platform:
- Pulls TuShare market data daily → generates technical indicators → evaluates trading strategies → performs single-stock backtests → visualizes results in web UI
- Chinese language frontend/documentation
- MVP focus: daily candles, technical indicators, signal generation, single-stock backtesting

## Build & Run Commands

### Local Development

```bash
# Start MongoDB + Redis
docker-compose up -d mongodb redis

# Backend (Terminal 1)
cd backend
pip install -e .
uvicorn app.main:app --reload --host 0.0.0.0 --port 9000 --reload-dir app

# Scheduler - runs daily jobs at 18:00 Shanghai time (Terminal 2)
cd backend
python scripts/scheduler.py

# Frontend (Terminal 3)
cd frontend
npm run dev
# Opens http://localhost:3000/freedom
```

### Docker Compose (Full Stack)

```bash
docker-compose up --build
# Frontend: http://localhost/freedom
# Backend API: http://localhost/freedom/api
```

### Data Loading Commands

```bash
# Pull daily market data
python backend/scripts/daily/pull_daily_history.py
python backend/scripts/daily/pull_daily_history.py --last-days 7
python backend/scripts/daily/pull_daily_history.py --start-date 20240101 --end-date 20240131

# Calculate technical indicators
python backend/scripts/one_time/calculate_indicators.py

# Calculate trading signals
python backend/scripts/daily/calculate_signal.py --given-date 20250126
python backend/scripts/daily/calculate_signal.py --start-date 20240101 --end-date 20240131

# Compact Parquet files
python backend/scripts/daily/compact_daily_parquet.py
python backend/scripts/daily/compact_daily_parquet.py --ts-code 000001.SZ --year 2024
```

## Architecture

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Data Source | TuShare (Chinese stock API) |
| Data Storage | Parquet (raw data), DuckDB (queries/meta) |
| Backend | FastAPI (Python 3.11+), port 9000 |
| Metadata DB | MongoDB 7 |
| Cache | Redis 7 (optional) |
| Frontend | Next.js 14, React 18, ECharts 5, port 3000 |
| Reverse Proxy | Nginx (basePath=/freedom) |
| Scheduler | APScheduler (daily 18:00 Asia/Shanghai) |

### Data Flow

```
TuShare API → Parquet files (data/raw/) → DuckDB queries
                                        ↓
MongoDB (stock_basic, daily_signal) ← FastAPI ← Next.js frontend
```

### Directory Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI entry point
│   ├── api/routes/          # API endpoints (stocks, daily_signals, stock_groups)
│   ├── services/            # Business logic
│   ├── data/                # DuckDB, MongoDB, TuShare clients
│   └── core/config.py       # Pydantic settings
├── scripts/
│   ├── scheduler.py         # APScheduler setup
│   ├── daily/               # Daily jobs (pull_daily_history, calculate_signal)
│   ├── one_time/            # Indicator calculation
│   └── strategy/            # Signal strategies (MaCross, EarlyBreakout, DailySignal)

frontend/
├── pages/
│   ├── index.js             # Stock list
│   ├── daily-signals.js     # Trading signals view
│   ├── stocks/[ts_code].js  # K-line chart + indicators
│   └── watchlist/           # User watchlists

data/
├── raw/daily/ts_code=*/year=*/    # K-line Parquet files
├── features/indicators/           # Technical indicator Parquet files
└── quant.duckdb                   # DuckDB database
```

### Key API Endpoints

- `GET /api/stocks` - Stock list with pagination/filtering
- `GET /api/stocks/{ts_code}/candles` - K-line data
- `GET /api/stocks/{ts_code}/features` - Technical indicators
- `GET /api/daily-signals` - Trading signals by date/stock/strategy
- `GET /api/stock-groups` - Watchlist management

## Environment Variables

Backend `.env`:
```ini
TUSHARE_TOKEN=<your_token>
DATA_DIR=./data
DUCKDB_PATH=./data/quant.duckdb
MONGODB_URL=mongodb://james:2x%23fdksma%21@localhost:27017/?authSource=admin
MONGODB_DB=freedom
```

Frontend (build-time):
```ini
NEXT_PUBLIC_API_BASE_URL=/freedom/api  # docker
NEXT_PUBLIC_API_BASE_URL=http://localhost:9000/api  # local dev
```

## Conventions

- **Stock codes**: Use `ts_code` format (e.g., `000001.SZ`)
- **Date formats**: `YYYYMMDD` internally, `YYYY-MM-DD` for user input
- **Technical indicators**: MA (5,10,20,30,60,120,200,250,500), MACD, RSI(14), KDJ(9), Bollinger Bands(20)
- **Signal types**: BUY, SELL, HOLD

## Debugging

```bash
# Backend logs
docker-compose logs -f backend

# Test API
curl http://localhost:9000/api/stocks

# Check Parquet data
ls -la data/raw/daily/ts_code=000001.SZ/year=2024/

# DuckDB query
duckdb data/quant.duckdb "SELECT COUNT(*) FROM adj_factor;"
```
