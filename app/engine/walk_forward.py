from collections.abc import Callable
from itertools import product

import pandas as pd

from app.engine.metrics import compute_metrics
from app.engine.runner import run_backtest, run_signals
from app.engine.strategies import get_strategy


def parameter_combinations(parameter_grid: dict[str, list[int | float]]) -> list[dict]:
    names = list(parameter_grid)
    values = [parameter_grid[name] for name in names]
    if not names or any(not options for options in values):
        raise ValueError("parameter_grid must contain at least one non-empty parameter list")
    combinations = [dict(zip(names, values_, strict=True)) for values_ in product(*values)]
    if len(combinations) > 100:
        raise ValueError("Parameter search is limited to 100 combinations")
    return combinations


def run_walk_forward(
    data: pd.DataFrame,
    strategy_name: str,
    parameter_grid: dict[str, list[int | float]],
    train_points: int,
    test_points: int,
    initial_capital: float = 10_000,
    commission: float = 0,
    slippage_bps: float = 0,
    execution_model: str = "next_open",
    position_size_pct: float = 100,
    stop_loss_pct: float | None = None,
    take_profit_pct: float | None = None,
    fractional_shares: bool = True,
    rank_by: str = "sharpe",
    progress_callback: Callable[[float], None] | None = None,
) -> dict:
    """Optimize on rolling training windows and evaluate untouched test windows."""
    if train_points < 20 or test_points < 5:
        raise ValueError("train_points must be at least 20 and test_points at least 5")
    if len(data) < train_points + test_points:
        raise ValueError(
            f"Walk-forward analysis needs at least {train_points + test_points} rows; got {len(data)}"
        )

    configurations = parameter_combinations(parameter_grid)
    folds = []
    compounded_equity = float(initial_capital)
    test_starts = [
        value
        for value in range(train_points, len(data), test_points)
        if min(value + test_points, len(data)) - value >= 2
    ]
    for fold_index, test_start in enumerate(test_starts, start=1):
        test_end = min(test_start + test_points, len(data))
        if test_end - test_start < 2:
            break
        training = data.iloc[test_start - train_points : test_start]
        candidates = []
        for params in configurations:
            try:
                result = run_backtest(
                    training,
                    get_strategy(strategy_name, params),
                    initial_capital,
                    commission,
                    slippage_bps,
                    execution_model,
                    position_size_pct,
                    stop_loss_pct,
                    take_profit_pct,
                    fractional_shares,
                )
                metrics = compute_metrics(result.frame, result.trades, initial_capital)
            except ValueError:
                continue
            candidates.append((metrics[rank_by], params, metrics))
        if not candidates:
            raise ValueError("No valid parameter combinations were available for training")
        _, best_params, training_metrics = max(candidates, key=lambda candidate: candidate[0])

        # Generate indicators with training context, but execute only on unseen rows.
        context = data.iloc[test_start - train_points : test_end]
        signaled = get_strategy(strategy_name, best_params).generate_signals(context)
        test_signals = signaled.iloc[train_points:].copy()
        if execution_model == "next_open":
            # Use the final training signal at the first unseen open without
            # carrying any training-period position into the test portfolio.
            test_signals["signal"] = signaled["signal"].shift(1).iloc[train_points:].to_numpy()
            test_result = run_signals(
                test_signals,
                compounded_equity,
                commission,
                slippage_bps,
                signal_delay=0,
                execution_price_column="open",
                position_size_pct=position_size_pct,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
                fractional_shares=fractional_shares,
            )
        elif execution_model == "same_close":
            test_result = run_signals(
                test_signals,
                compounded_equity,
                commission,
                slippage_bps,
                signal_delay=0,
                execution_price_column="close",
                position_size_pct=position_size_pct,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
                fractional_shares=fractional_shares,
            )
        else:
            raise ValueError("execution_model must be 'next_open' or 'same_close'")
        test_metrics = compute_metrics(test_result.frame, test_result.trades, compounded_equity)
        compounded_equity = test_metrics["final_equity"]
        folds.append(
            {
                "train_start": pd.Timestamp(training.index[0]).isoformat(),
                "train_end": pd.Timestamp(training.index[-1]).isoformat(),
                "test_start": pd.Timestamp(test_signals.index[0]).isoformat(),
                "test_end": pd.Timestamp(test_signals.index[-1]).isoformat(),
                "params": best_params,
                "training_metrics": training_metrics,
                "test_metrics": test_metrics,
                "trades": test_result.trades,
            }
        )
        if progress_callback:
            progress_callback(fold_index / len(test_starts))

    total_return = compounded_equity / initial_capital - 1
    return {
        "strategy": strategy_name,
        "rank_by": rank_by,
        "fold_count": len(folds),
        "initial_capital": initial_capital,
        "final_equity": round(compounded_equity, 2),
        "total_return": round(total_return, 8),
        "folds": folds,
    }
