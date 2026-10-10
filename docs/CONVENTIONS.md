# Conventions

- Use lowercase OHLCV column names and a date-like DataFrame index inside the engine.
- Strategy signals represent desired regimes: `1` means long, `-1` means flat, and `0` means no established regime.
- Keep the engine deterministic and independent of FastAPI and SQLAlchemy.
- Validate all public request parameters and return actionable 422 errors.
- Add regression tests for every strategy, metric, and API behavior change.
- Never commit secrets, local databases, virtual environments, caches, or generated test output.
