# AGENTS.md - Freedom Quant Platform

> This file provides essential guidance for AI coding agents working on this repository.

## Project Overview

**Freedom Quant Platform** (自用量化策略平台) is a Chinese A-share stock quantitative research and backtesting platform for personal use.

**Core Workflow:**
- Daily automated data pull from TuShare (after market close)
- Generate technical indicators and features
- Strategy signal generation (BUY/SELL/HOLD)
- Single-stock backtesting
- Web-based visualization (K-line charts + indicators + trading signals)

**Documentation Language:** Chinese (comments, UI, and most docs are in Chinese)

---

## Technology Stack

| Layer | Technology | Version/Notes |
|-------|-----------|---------------|
| Data Source | TuShare API | Chinese A-share market data |
| Raw Data Storage | Parquet | Partitioned by `ts_code/year` |
| Query Engine | DuckDB | Local analytics, metadata storage |
| Metadata DB | MongoDB 7 | stock_basic, daily_signal, users, groups |
| Cache (Optional) | Redis 7 | Hot data caching |
| Backend | FastAPI | Python 3.11+, port 9000 |
| Frontend | Next.js 14 | React 18, ECharts 5, port 3000 |
| Reverse Proxy | Nginx | basePath `/freedom` |
| Scheduler | APScheduler | Daily at 18:00 Asia/Shanghai |

---

## Project Structure

```
freedom/
├── backend/                    # FastAPI backend
│   ├── app/
│   │   ├── main.py            # FastAPI entry point
│   │   ├── api/
│   │   │   ├── routers.py     # Router aggregation
│   │   │   ├── deps.py        # Authentication dependencies
│   │   │   └── routes/        # API endpoints
│   │   │       ├── stocks.py
│   │   │       ├── daily_signals.py
│   │   │       ├── stock_groups.py
│   │   │       ├── strategies.py
│   │   │       ├── backtests.py
│   │   │       ├── auth.py
│   │   │       ├── users.py
│   │   │       └── health.py
│   │   ├── core/
│   │   │   └── config.py      # Pydantic settings
│   │   ├── data/
│   │   │   ├── duckdb_store.py    # DuckDB operations
│   │   │   ├── mongo.py           # MongoDB connection
│   │   │   ├── mongo_stock.py     # Stock basic operations
│   │   │   ├── mongo_users.py     # User management
│   │   │   ├── mongo_groups.py    # Stock groups/watchlists
│   │   │   ├── mongo_refresh_tokens.py
│   │   │   └── tushare_client.py  # TuShare API client
│   │   ├── services/
│   │   │   └── stocks_service.py
│   │   ├── models/
│   │   │   └── daily_signal.py
│   │   ├── schemas/
│   │   │   ├── auth.py
│   │   │   └── users.py
│   │   └── strategies/        # Strategy templates (minimal)
│   ├── scripts/
│   │   ├── scheduler.py       # APScheduler setup
│   │   ├── daily/             # Daily scheduled jobs
│   │   │   ├── pull_daily_history.py
│   │   │   ├── calculate_signal.py
│   │   │   └── compact_daily_parquet.py
│   │   ├── one_time/          # One-time data processing
│   │   │   ├── calculate_indicators.py
│   │   │   └── pull_stock_history.py
│   │   └── strategy/          # Signal strategies
│   │       ├── base_strategy.py
│   │       ├── first.py
│   │       ├── second.py
│   │       └── third.py
│   ├── pyproject.toml         # Python dependencies
│   ├── Dockerfile             # Production build
│   ├── Dockerfile.base        # Base image with dependencies
│   └── .env.example           # Environment template
│
├── frontend/                  # Next.js frontend
│   ├── pages/
│   │   ├── index.js          # Stock list page
│   │   ├── daily-signals.js  # Trading signals view
│   │   ├── login.js          # Authentication
│   │   ├── users.js          # User management
│   │   ├── stocks/
│   │   │   └── [ts_code].js  # K-line chart page
│   │   └── watchlist/        # User watchlists
│   ├── lib/
│   │   └── api.js            # API client utilities
│   ├── styles/
│   ├── package.json          # Node dependencies
│   ├── next.config.js        # Next.js config (basePath=/freedom)
│   ├── Dockerfile
│   └── Dockerfile.base
│
├── data/                      # Data storage (gitignored)
│   ├── raw/
│   │   ├── daily/ts_code=*/year=*/part-*.parquet
│   │   ├── daily_basic/ts_code=*/year=*/part-*.parquet
│   │   ├── daily_limit/ts_code=*/year=*/part-*.parquet
│   │   └── adj_factor/...
│   ├── features/indicators/   # Technical indicator Parquet files
│   ├── quant.duckdb          # DuckDB database
│   └── mongo/                # MongoDB data volume
│
├── nginx/
│   └── nginx.conf            # Reverse proxy configuration
│
├── docker-compose.yaml       # Full stack orchestration
├── logs/                     # Application logs
└── scripts/                  # Utility scripts
```

---

## Build and Run Commands

### Local Development (Recommended)

```bash
# 1. Start infrastructure services
docker-compose up -d mongodb redis

# 2. Backend (Terminal 1)
cd backend
pip install -e .
uvicorn app.main:app --reload --host 0.0.0.0 --port 9000 --reload-dir app

# 3. Scheduler (Terminal 2) - Optional, runs daily jobs
cd backend
python scripts/scheduler.py

# 4. Frontend (Terminal 3)
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

---

## Data Pipeline Commands

### Pull Daily Market Data

```bash
# Pull today's data
python backend/scripts/daily/pull_daily_history.py

# Pull last N days
python backend/scripts/daily/pull_daily_history.py --last-days 7

# Pull specific date range
python backend/scripts/daily/pull_daily_history.py --start-date 20240101 --end-date 20240131
```

### Sync Stock Technical Factors

```bash
# Pull latest trading day factors
python backend/scripts/daily/sync_stk_factor_pro.py --last-days 1

# Pull specific date range
python backend/scripts/daily/sync_stk_factor_pro.py --start-date 20240101 --end-date 20240131
```

**Primary fields written:**
- Moving Averages: MA5, MA10, MA20, MA30, MA60, MA90, MA250
- MACD: macd, macd_signal, macd_hist
- RSI: rsi6, rsi12, rsi24
- KDJ(9): kdj_k, kdj_d, kdj_j
- Bollinger Bands(20): boll_upper, boll_middle, boll_lower
- Extra factors: atr, cci, wr, wr1, updays, downdays, pe, pe_ttm, pb, turnover_rate, turnover_rate_f, volume_ratio

### Calculate Trading Signals

```bash
# Calculate for specific date
python backend/scripts/daily/calculate_signal.py --given-date 20250126

# Calculate date range
python backend/scripts/daily/calculate_signal.py --start-date 20240101 --end-date 20240131
```

**Strategies:** `EarlyBreakoutSignalModel`, `DailySignalModel`
**Storage:** MongoDB `daily_signal` collection

### Parquet Compaction

```bash
# Compact all data
python backend/scripts/daily/compact_daily_parquet.py

# Compact specific stock/year
python backend/scripts/daily/compact_daily_parquet.py --ts-code 000001.SZ --year 2024
```

Compaction removes duplicates (using `SELECT DISTINCT`) and merges multiple small Parquet files.

---

## Key API Endpoints

All endpoints require authentication (except `/health` and `/auth/*`):

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/auth/login` | POST | User login |
| `/api/auth/refresh` | POST | Refresh access token |
| `/api/stocks` | GET | Stock list (paginated, filterable) |
| `/api/stocks/industries` | GET | List all industries |
| `/api/stocks/sync` | POST | Sync stock_basic from TuShare |
| `/api/stocks/{ts_code}/candles` | GET | K-line data |
| `/api/stocks/{ts_code}/features` | GET | Technical indicators |
| `/api/daily-signals` | GET | Trading signals |
| `/api/daily-signals/dates` | GET | Available signal dates |
| `/api/daily-signals/strategies` | GET | Available strategies |
| `/api/stock-groups` | GET/POST | Watchlist management |
| `/api/strategies` | GET/POST | Strategy CRUD |
| `/api/backtests` | GET/POST | Backtest operations |

---

## Environment Variables

### Backend (`.env` file in `backend/`)

```ini
# Required
TUSHARE_TOKEN=<your_tushare_token>
MONGODB_URL=mongodb://james:2x%23fdksma%21@localhost:27017/?authSource=admin
MONGODB_DB=freedom

# Optional (have defaults)
DATA_DIR=./data
DUCKDB_PATH=./data/quant.duckdb
REDIS_URL=redis://localhost:6379/0
LOG_LEVEL=INFO

# Security
JWT_SECRET=change-me
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRES_MINUTES=120
REFRESH_TOKEN_EXPIRES_DAYS=7

# Admin user (created on startup)
ADMIN_USERNAME=james
ADMIN_PASSWORD=james1031

# CORS
CORS_ALLOW_ORIGINS=http://localhost:3000
```

### Frontend (build-time)

```ini
# Local development
NEXT_PUBLIC_API_BASE_URL=http://localhost:9000/api

# Docker deployment
NEXT_PUBLIC_API_BASE_URL=/freedom/api
```

---

## Code Style Guidelines

### Python (Backend)

- **Formatter:** Black-compatible style
- **Linter:** Flake8 (max line length: 150, ignores E501)
- **Type hints:** Use Python 3.11+ syntax (`str | None`, `list[dict[str, object]]`)
- **Import style:** `from __future__ import annotations` at top for forward references

### JavaScript (Frontend)

- **Framework:** Next.js 14 with Pages Router
- **Styling:** CSS files in `styles/`
- **API calls:** Use `lib/api.js` -> `apiFetch()` utility

---

## Conventions

### Stock Codes
- Use `ts_code` format: `000001.SZ`, `600000.SH`
- Not `symbol` (which is just the numeric part)

### Date Formats
- **Internal storage:** `YYYYMMDD` (e.g., `20250126`)
- **User input:** Accepts both `YYYYMMDD` and `YYYY-MM-DD`
- **Display:** Usually `YYYY-MM-DD`

### Signal Types
- `BUY` - Buy signal
- `SELL` - Sell signal  
- `HOLD` - No action

### Data Partitioning
Parquet files are partitioned as:
```
data/raw/daily/ts_code=000001.SZ/year=2024/part-*.parquet
```

---

## Testing

**Note:** The project currently has no formal test suite. Testing is done via:

1. **Manual API testing:**
   ```bash
   curl http://localhost:9000/api/stocks
   curl http://localhost:9000/api/health
   ```

2. **Data verification:**
   ```bash
   # Check Parquet data
   ls -la data/raw/daily/ts_code=000001.SZ/year=2024/
   
   # DuckDB query
   duckdb data/quant.duckdb "SELECT COUNT(*) FROM adj_factor;"
   ```

3. **Docker logs:**
   ```bash
   docker-compose logs -f backend
   ```

---

## Deployment Architecture

```
┌─────────────┐
│   Nginx     │  Port 80, routes /freedom/*
└──────┬──────┘
       │
   ┌───┴───┐
   │       │
   ▼       ▼
┌──────┐ ┌──────┐
│Frontend│ │Backend│
│:3000  │ │:9000  │
└──┬───┘ └───┬──┘
   │         │
   │    ┌────┴────┐
   │    │         │
   │    ▼         ▼
   │ ┌──────┐  ┌──────┐
   │ │MongoDB│  │Redis │
   │ │:27017│  │:6379 │
   │ └──────┘  └──────┘
   │
   ▼
┌─────────┐
│ DuckDB  │  File-based at data/quant.duckdb
│ Parquet │  Partitioned files at data/raw/
└─────────┘
```

---

## Security Considerations

1. **Authentication:** JWT-based with access and refresh tokens
2. **Default Credentials:** Change `ADMIN_PASSWORD` and `JWT_SECRET` in production
3. **Cookie Security:** Set `AUTH_COOKIE_SECURE=true` for HTTPS deployments
4. **CORS:** Restrict `CORS_ALLOW_ORIGINS` to known origins in production
5. **MongoDB:** Uses authentication (username/password in connection string)
6. **TuShare Token:** Stored in environment variable, not in code

---

## Troubleshooting

### Backend won't start
- Check MongoDB is running: `docker-compose ps mongodb`
- Verify `.env` file exists in `backend/` directory
- Check logs: `docker-compose logs backend`

### Missing stock data
- Run sync: `curl -X POST http://localhost:9000/api/stocks/sync`
- Check TuShare token is valid

### DuckDB lock errors
- The app has retry logic for lock contention
- Stop scheduler if running manual data operations

### Frontend API errors
- Verify `NEXT_PUBLIC_API_BASE_URL` is set correctly
- Check CORS settings match your origin

---

## Useful References

- **TuShare API:** https://tushare.pro/document/2
- **FastAPI:** https://fastapi.tiangolo.com/
- **DuckDB:** https://duckdb.org/docs/
- **Next.js:** https://nextjs.org/docs
- **ECharts:** https://echarts.apache.org/en/option.html
