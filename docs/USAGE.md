# Usage

## Configuration

AlphaTest uses `sqlite:///./alphatest.db` by default. Set `DATABASE_URL` to a SQLAlchemy-compatible PostgreSQL URL to use PostgreSQL. Keep credentials in an untracked environment file or secret manager.

Apply schema migrations with `alembic upgrade head`. The Docker Compose stack applies them automatically before starting the API.

Set `ALPHATEST_API_KEY` to require the same value in the `X-API-Key` header for every `/api/` route. Health and readiness endpoints remain unauthenticated for container probes. Leave the variable unset for local-only development without authentication.

Set `ALPHATEST_ENGINE_REVISION` to the deployed release or commit identifier. It defaults to `1.0.0` for local use and is stored with each new backtest result.

## Data ingestion

```bash
python -m app.data.ingest --ticker MSFT --start 2020-01-01 --end 2025-01-01
```

Ingestion is idempotent for SQLite. The API can also read existing `data/raw/{TICKER}_yahoo.csv` files when database data is unavailable.
Downloaded OHLC prices are adjusted for splits and distributions to avoid artificial strategy returns around corporate actions.

## API example

```bash
curl -X POST http://localhost:8000/api/backtest \
  -H 'Content-Type: application/json' \
  -d '{
    "ticker": "AAPL",
    "strategy": "sma",
    "params": {"short_window": 20, "long_window": 50},
    "start_date": "2020-01-01",
    "end_date": "2025-01-01",
    "initial_capital": 10000,
    "commission": 0
  }'
```

Use `/docs` for the complete interactive API contract. A 422 response contains an actionable `detail` describing missing data or invalid parameters.

Available strategies are `sma`, `rsi`, `macd`, and `bollinger`. Retrieve their descriptions and default parameters from `GET /api/strategies`.

`POST /api/portfolio` accepts up to 20 ticker/strategy components whose `allocation_pct` values total 100. It simulates each allocation independently, aligns them on their common trading calendar, and returns combined equity, a weighted buy-and-hold benchmark, component attribution, and ticker-tagged trades.

Use `GET /api/results` for recent run summaries and `GET /api/results/{id}` for a saved run including its complete trade log.

Every `POST /api/backtest` response includes `provenance`: the engine revision, canonical request fingerprint, normalized OHLCV fingerprint, row count, and observed input dates. Result summaries expose these identifiers, while result detail also includes the immutable request snapshot. Matching request and data fingerprints indicate the same declared configuration and input series; each execution still creates its own result record.

Use `POST /api/configurations` to save a named backtest request. Configurations can be listed, retrieved, fully replaced, and deleted through `/api/configurations` and `/api/configurations/{id}`. `POST /api/configurations/{id}/run` executes the stored setup and creates a normal immutable result.

Use `POST /api/results/{id}/rerun` to repeat a stored result from its request snapshot. The new record sets `source_result_id` to the original result. Results created before request snapshots were introduced return HTTP 409 because they cannot be reconstructed safely.

The Streamlit sidebar can save the currently selected setup. Enable **Manage saved configurations** to inspect, execute, or delete named configurations. Load result history to select and rerun a prior result; configured runs and reruns are displayed through the same equity, drawdown, trade, metric, and provenance views as direct runs.

Backtest and portfolio responses include per-bar drawdown plus monthly and yearly return series. Metrics include CAGR, Sharpe, Sortino, Calmar, annualized volatility, maximum drawdown and duration, exposure, turnover, expectancy, profit factor, average win/loss, average trade duration, commissions, and estimated slippage cost. The first calendar period is measured from the initial equity observation so partial starting months and years remain visible.

## Execution assumptions

The default `next_open` execution model calculates a signal from one bar's close and executes it at the following bar's open. This avoids trading on a closing value before it would have been observable. Set `slippage_bps` to apply adverse price movement to every fill and `commission` for a fixed charge per fill. The `same_close` model is available for compatibility and sensitivity analysis, but it can overstate results unless the strategy genuinely has access to executable closing-auction prices.

Set `position_size_pct` to keep part of the portfolio in cash. Optional `stop_loss_pct` and `take_profit_pct` values create price-based exits relative to each entry. With daily OHLCV bars, gap openings execute at the open; otherwise the configured threshold is used. If a bar touches both thresholds and intraday ordering is unknowable, AlphaTest conservatively assumes the stop-loss occurred first.

Set `fractional_shares` to `false` to floor entries to whole shares and retain the remainder as cash. It defaults to `true`, which is useful for normalized strategy comparisons and assets that support fractional execution.

## Walk-forward evaluation

`POST /api/walk-forward` accepts a strategy, a parameter grid, and training/testing window sizes measured in observations. Each fold selects parameters using only its training window and compounds returns from the subsequent unseen testing window. Searches are limited to 100 parameter combinations.

## Durable research jobs

Run `python -m app.jobs` beside the API, or use Docker Compose, which starts the worker automatically. Submit a sweep, walk-forward run, or portfolio to `POST /api/jobs` using this envelope:

```json
{
  "kind": "sweep",
  "input_payload": {
    "ticker": "AAPL",
    "strategy": "sma",
    "parameter_grid": {"short_window": [10, 20], "long_window": [50, 100]},
    "start_date": "2018-01-01",
    "end_date": "2025-12-31"
  }
}
```

The API returns HTTP 202 with a job identifier. Poll `GET /api/jobs/{job_id}` for `queued`, `running`, `completed`, `failed`, or `cancelled` state; completed output is stored in `result`. `GET /api/jobs` returns recent work. `POST /api/jobs/{job_id}/cancel` immediately cancels queued work and requests cooperative cancellation of running work. A worker that disappears loses its lease, allowing a later worker to requeue and retry the job.
