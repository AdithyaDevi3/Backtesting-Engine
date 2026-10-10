# Architecture

AlphaTest has five local components:

1. Data ingestion downloads daily OHLCV data from Yahoo Finance and stores normalized rows.
2. The engine generates strategy signals, simulates a long-only portfolio, and calculates metrics without depending on HTTP or database code.
3. FastAPI validates requests, loads market data, runs the engine, and persists results.
4. Streamlit calls the API and renders metric cards, an interactive equity curve, and trade history.
5. A separate worker claims durable research jobs for sweeps, walk-forward evaluations, and portfolios.

Long-running research can be submitted to the `research_jobs` table through the API. The worker atomically claims queued work, renews a lease at progress boundaries, and persists the result or a bounded error message. A stopped worker leaves the job durable; another worker requeues it after its lease expires. Queued cancellation is immediate, while running cancellation is cooperative at sweep combinations, walk-forward folds, and portfolio components. The original synchronous endpoints remain available for small interactive requests.

Walk-forward evaluation is kept in the engine layer. Indicator state receives historical training context, while portfolio execution begins only on each out-of-sample testing window. This prevents training-period trades from leaking into reported test performance.

Signals and fills are separate engine concepts. By default, signals calculated from a closing bar are delayed and filled at the next available open with adverse slippage. Portfolios are marked to each bar's close, so reported equity does not use fill prices as valuation prices.

Risk controls are evaluated before strategy exits on each bar. Gap-aware stop and target fills use daily open, high, and low values; ambiguous bars prioritize the stop. This is deliberately conservative but cannot reproduce true intraday event ordering from daily data.

Multi-asset portfolios allocate starting capital before simulation, run each component independently, and aggregate them on the intersection of their trading calendars. Component benchmarks are normalized and weighted by starting allocation. This avoids forward-filling across markets that were not simultaneously tradable, at the cost of excluding non-common dates.

SQLite is the zero-configuration default. PostgreSQL can be selected through `DATABASE_URL`, with schema changes managed by Alembic. API callers are outside the application trust boundary; request schemas and strategy validation reject malformed configurations. Deployments can set `ALPHATEST_API_KEY` for shared-secret protection, though TLS termination and stronger identity controls remain the responsibility of the hosting environment.

Each persisted single-asset backtest stores an immutable request snapshot plus SHA-256 fingerprints for the canonical request and normalized OHLCV input. The record also captures the engine revision, observed data range, row count, completion status, and optional source-result identifier. The request fingerprint changes when strategy or execution assumptions change; the data fingerprint changes when any normalized input bar changes. Deployments should set `ALPHATEST_ENGINE_REVISION` to a release or commit identifier so results can be traced to deployed code even when Git metadata is unavailable.

Named saved configurations are mutable templates rather than execution records. Creating or updating a configuration validates the same fields as a direct backtest request. Running a configuration produces a new immutable backtest result. Rerunning a result reconstructs its stored request snapshot, creates another immutable result, and records the original result ID as lineage; it never overwrites prior evidence.

Application startup applies all pending Alembic migrations before accepting requests. Startup fails if a migration cannot complete, preventing the API from operating against a partially upgraded schema.
