# Endpoints

Use the OpenAPI document for exact schemas. This file is the working index.

## Market Basics

- `GET /stocks/basic`
- `GET /stocks/basic/{ts_code}`
- `GET /stocks/search`
- `GET /stocks/daily/snapshot`
- `GET /stocks/{ts_code}/daily`
- `GET /stocks/{ts_code}/daily/recent`
- `POST /stocks/daily/batch`

## Screening And Indicators

- `POST /stocks/daily/stats/screen`
- `GET /stocks/{ts_code}/daily-basic`
- `GET /stocks/daily-basic/snapshot`
- `GET /stocks/{ts_code}/indicators`

## Industry

- `GET /industry/shenwan/tree`
- `GET /industry/shenwan/members`
- `GET /industry/shenwan/daily`
- `GET /industry/shenwan/daily/ranking`
- `GET /industry/citic/tree`
- `GET /industry/citic/members`
- `GET /industry/citic/daily`

## Index And Calendar

- `GET /market-index/daily-basic`
- `GET /market-index/factors`
- `GET /trade-calendar`
- `GET /trade-calendar/latest-trade-date`

## Financials And Dividends

- `GET /stocks/{ts_code}/financials/indicators`
- `GET /stocks/{ts_code}/financials/income`
- `GET /stocks/{ts_code}/financials/balance`
- `GET /stocks/{ts_code}/financials/cashflow`
- `POST /stocks/financials/indicators/batch`
- `GET /stocks/financials/indicators/screen`
- `GET /stocks/{ts_code}/dividends`
- `GET /stocks/{ts_code}/dividends/summary`
- `GET /stocks/dividends/screen`

## Insider, Macro, And Events

- `GET /stocks/{ts_code}/insider-trades`
- `GET /market/insider-trades/latest`
- `GET /macro/money-supply`
- `GET /macro/lpr`
- `GET /macro/pmi`
- `GET /macro/cpi-ppi`
- `GET /macro/social-financing`
- `GET /stocks/{ts_code}/events/buyback`
- `GET /market/events/ma-restructure`
- `GET /stocks/{ts_code}/events/holder-changes`
