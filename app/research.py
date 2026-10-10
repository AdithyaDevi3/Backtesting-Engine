from collections.abc import Callable

from sqlalchemy.orm import Session

from app.data.loader import load_ohlcv
from app.engine import (
    PortfolioComponentResult,
    combine_portfolio,
    compute_metrics,
    periodic_returns,
    run_backtest,
)
from app.engine.strategies import get_strategy
from app.engine.walk_forward import parameter_combinations, run_walk_forward
from app.schemas import PortfolioRequest, SweepRequest, WalkForwardRequest


ProgressCallback = Callable[[float], None]


def run_sweep(
    db: Session,
    request: SweepRequest,
    progress_callback: ProgressCallback | None = None,
) -> dict:
    combinations = parameter_combinations(request.parameter_grid)
    data = load_ohlcv(db, request.ticker, request.start_date, request.end_date)
    ranked = []
    total = len(combinations)
    for index, params in enumerate(combinations, start=1):
        try:
            result = run_backtest(
                data,
                get_strategy(request.strategy, params),
                request.initial_capital,
                request.commission,
                request.slippage_bps,
                request.execution_model,
                request.position_size_pct,
                request.stop_loss_pct,
                request.take_profit_pct,
                request.fractional_shares,
            )
        except ValueError as exc:
            raise ValueError(f"Invalid parameters {params}: {exc}") from exc
        ranked.append(
            {
                "params": params,
                "metrics": compute_metrics(result.frame, result.trades, request.initial_capital),
            }
        )
        if progress_callback:
            progress_callback(index / total)

    ranked.sort(key=lambda item: item["metrics"][request.rank_by], reverse=True)
    return {
        "ticker": request.ticker,
        "strategy": request.strategy,
        "rank_by": request.rank_by,
        "results": ranked,
    }


def run_walk_forward_research(
    db: Session,
    request: WalkForwardRequest,
    progress_callback: ProgressCallback | None = None,
) -> dict:
    data = load_ohlcv(db, request.ticker, request.start_date, request.end_date)
    result = run_walk_forward(
        data=data,
        strategy_name=request.strategy,
        parameter_grid=request.parameter_grid,
        train_points=request.train_points,
        test_points=request.test_points,
        initial_capital=request.initial_capital,
        commission=request.commission,
        slippage_bps=request.slippage_bps,
        execution_model=request.execution_model,
        position_size_pct=request.position_size_pct,
        stop_loss_pct=request.stop_loss_pct,
        take_profit_pct=request.take_profit_pct,
        fractional_shares=request.fractional_shares,
        rank_by=request.rank_by,
        progress_callback=progress_callback,
    )
    return {"ticker": request.ticker, **result}


def run_portfolio_research(
    db: Session,
    request: PortfolioRequest,
    progress_callback: ProgressCallback | None = None,
) -> dict:
    components = []
    total = len(request.components)
    for index, configuration in enumerate(request.components, start=1):
        allocation = request.initial_capital * configuration.allocation_pct / 100
        data = load_ohlcv(db, configuration.ticker, request.start_date, request.end_date)
        strategy = get_strategy(configuration.strategy, configuration.params)
        result = run_backtest(
            data,
            strategy,
            allocation,
            request.commission,
            request.slippage_bps,
            request.execution_model,
            request.position_size_pct,
            request.stop_loss_pct,
            request.take_profit_pct,
            request.fractional_shares,
        )
        components.append(
            PortfolioComponentResult(
                ticker=configuration.ticker,
                strategy=configuration.strategy,
                allocation=allocation,
                result=result,
            )
        )
        if progress_callback:
            progress_callback(index / total * 0.9)

    portfolio = combine_portfolio(components, request.initial_capital)
    curve = [
        {
            "date": timestamp.isoformat(),
            "benchmark": round(float(row["close"]), 6),
            "equity": round(float(row["equity"]), 6),
            "drawdown": round(float(row["drawdown"]), 8),
        }
        for timestamp, row in portfolio["frame"].iterrows()
    ]
    if progress_callback:
        progress_callback(1.0)
    return {
        "metrics": portfolio["metrics"],
        "periodic_returns": periodic_returns(portfolio["frame"]),
        "equity_curve": curve,
        "components": portfolio["components"],
        "trades": portfolio["trades"],
    }
