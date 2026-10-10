from dataclasses import dataclass

import pandas as pd

from app.engine.metrics import compute_metrics
from app.engine.runner import BacktestResult


@dataclass(frozen=True)
class PortfolioComponentResult:
    ticker: str
    strategy: str
    allocation: float
    result: BacktestResult


def combine_portfolio(
    components: list[PortfolioComponentResult], initial_capital: float
) -> dict:
    """Combine independently simulated allocations on their common calendar."""
    if not components:
        raise ValueError("Portfolio must contain at least one component")

    common_index = components[0].result.frame.index
    for component in components[1:]:
        common_index = common_index.intersection(component.result.frame.index)
    common_index = common_index.sort_values()
    if len(common_index) < 2:
        raise ValueError("Portfolio components do not share enough trading dates")

    combined_equity = pd.Series(0.0, index=common_index)
    combined_benchmark = pd.Series(0.0, index=common_index)
    active_positions = pd.Series(0.0, index=common_index)
    trades = []
    summaries = []

    for component in components:
        frame = component.result.frame.reindex(common_index)
        combined_equity = combined_equity.add(frame["equity"], fill_value=0)
        benchmark = frame["close"] / frame["close"].iloc[0] * component.allocation
        combined_benchmark = combined_benchmark.add(benchmark, fill_value=0)
        active_positions = active_positions.add((frame["position"] > 0).astype(float), fill_value=0)
        component_metrics = compute_metrics(
            component.result.frame, component.result.trades, component.allocation
        )
        summaries.append(
            {
                "ticker": component.ticker,
                "strategy": component.strategy,
                "allocation": round(component.allocation, 2),
                "contribution": round(
                    component_metrics["final_equity"] - component.allocation, 2
                ),
                "metrics": component_metrics,
            }
        )
        trades.extend({"ticker": component.ticker, **trade} for trade in component.result.trades)

    frame = pd.DataFrame(
        {
            "close": combined_benchmark,
            "equity": combined_equity,
            "position": active_positions,
        },
        index=common_index,
    )
    frame["returns"] = frame["equity"].pct_change().fillna(0.0)
    frame["drawdown"] = frame["equity"] / frame["equity"].cummax() - 1
    trades.sort(key=lambda trade: trade["date"])
    metrics = compute_metrics(frame, trades, initial_capital)
    return {"frame": frame, "trades": trades, "metrics": metrics, "components": summaries}
