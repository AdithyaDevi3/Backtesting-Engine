# AlphaTest

AlphaTest is a local-first quantitative backtesting application. It runs SMA crossover, RSI, MACD, and Bollinger-band strategies against historical OHLCV data, exposes configurable backtests through FastAPI, persists results in SQLite or PostgreSQL, and visualizes equity curves and trades in Streamlit.

## Quick start

Requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.data.ingest --ticker AAPL --start 2018-01-01
uvicorn app.main:app --reload
```

In additional terminals, start the durable research worker and dashboard:

```bash
source .venv/bin/activate
python -m app.jobs
streamlit run dashboard/app.py
```

Open the API documentation at `http://localhost:8000/docs` and the dashboard at `http://localhost:8501`.

For a PostgreSQL-backed local stack, copy `.env.example` to `.env`, replace its placeholder, and run `docker compose up --build`. Never reuse the local password in a shared environment.

## Features

- SMA crossover, RSI, MACD, and Bollinger-band strategies with validated parameters
- Long-only portfolio simulation with configurable capital and commissions
- Next-bar-open execution by default, with configurable slippage and a same-close compatibility mode
- Fractional or whole-share position sizing with optional stop-loss and take-profit exits
- Auditable equity, drawdown, and trade logs with risk, turnover, expectancy, exposure, and calendar-return analytics
- Reproducible experiment provenance with canonical request and OHLCV fingerprints, engine revision, and input coverage
- Named reusable configurations and lineage-preserving result reruns
- `POST /api/backtest`, `/api/compare`, and `/api/sweep` endpoints
- Durable `POST /api/jobs` queue for sweeps, walk-forward runs, and portfolios
- Rolling walk-forward parameter selection and out-of-sample evaluation
- Weighted multi-asset portfolios with per-component strategies and attribution
- Persistent result history through `GET /api/results`
- SQLite by default and PostgreSQL through `DATABASE_URL`
- Alembic schema migrations and optional API-key protection
- Lease-based worker recovery, persisted progress, errors, results, and cancellation requests
- Streamlit and Plotly dashboard
- Dashboard portfolio lab and CSV exports for equity curves and trades

See [usage](docs/USAGE.md), [architecture](docs/ARCHITECTURE.md), and [project conventions](docs/CONVENTIONS.md) for details. This project is intended for personal research and education; see [personal-use guidance](docs/PERSONAL_USE.md) before relying on results.

## Validation

```bash
pytest -q
```

Backtests are simplified research simulations, not investment advice. They model configurable slippage and adjusted daily data, but not order-book liquidity, taxes, short selling, or the unknowable intraday path within an OHLC bar.
