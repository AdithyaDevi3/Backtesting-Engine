import math

import pandas as pd


def compute_metrics(frame: pd.DataFrame, trades: list[dict], initial_capital: float) -> dict:
    if frame.empty or "equity" not in frame:
        raise ValueError("Backtest frame must include equity values")

    equity = frame["equity"].astype(float)
    returns = equity.pct_change().dropna()
    final_equity = float(equity.iloc[-1])
    total_return = final_equity / initial_capital - 1
    volatility = float(returns.std(ddof=0) * math.sqrt(252)) if len(returns) else 0.0
    sharpe = 0.0
    if len(returns) and returns.std(ddof=0) > 0:
        sharpe = float(returns.mean() / returns.std(ddof=0) * math.sqrt(252))
    drawdown = equity / equity.cummax() - 1
    max_drawdown = float(drawdown.min())
    underwater = drawdown < 0
    drawdown_groups = (~underwater).cumsum()
    drawdown_lengths = underwater.groupby(drawdown_groups).sum()
    max_drawdown_duration = int(drawdown_lengths.max()) if len(drawdown_lengths) else 0
    trough_position = int(drawdown.values.argmin())
    peak_position = int(equity.iloc[: trough_position + 1].values.argmax())
    recovery_position = None
    if trough_position >= peak_position:
        peak_equity = float(equity.iloc[: trough_position + 1].max())
        recovered = equity.iloc[trough_position + 1 :] >= peak_equity
        if recovered.any():
            recovery_position = int(equity.index.get_loc(recovered[recovered].index[0]))
    years = max((pd.Timestamp(frame.index[-1]) - pd.Timestamp(frame.index[0])).days / 365.25, 0)
    cagr = (final_equity / initial_capital) ** (1 / years) - 1 if years > 0 else total_return
    downside = returns[returns < 0]
    sortino = 0.0
    if len(downside) and downside.std(ddof=0) > 0:
        sortino = float(returns.mean() / downside.std(ddof=0) * math.sqrt(252))
    calmar = float(cagr / abs(max_drawdown)) if max_drawdown < 0 else 0.0
    exposure = float((frame["position"] > 0).mean()) if "position" in frame else 0.0
    benchmark_return = float(frame["close"].iloc[-1] / frame["close"].iloc[0] - 1)

    completed = []
    durations = []
    open_trades: dict[str, dict] = {}
    for trade in trades:
        trade_key = trade.get("ticker", "__single_asset__")
        if trade["type"] == "buy":
            open_trades[trade_key] = trade
        elif trade["type"] == "sell" and trade_key in open_trades:
            open_trade = open_trades.pop(trade_key)
            pnl = (
                (trade["price"] - open_trade["price"]) * trade["quantity"]
                - trade["commission"]
                - open_trade["commission"]
            )
            completed.append(pnl)
            duration = pd.Timestamp(trade["date"]) - pd.Timestamp(open_trade["date"])
            durations.append(max(duration.total_seconds() / 86_400, 0.0))
    wins = [pnl for pnl in completed if pnl > 0]
    losses = [pnl for pnl in completed if pnl < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = sum(wins) / abs(sum(losses)) if losses else (float("inf") if wins else 0.0)
    average_equity = float(equity.mean())
    traded_notional = sum(float(trade["price"]) * float(trade["quantity"]) for trade in trades)
    turnover = traded_notional / average_equity if average_equity > 0 else 0.0
    expectancy = sum(completed) / len(completed) if completed else 0.0
    average_win = gross_profit / len(wins) if wins else 0.0
    average_loss = gross_loss / len(losses) if losses else 0.0
    slippage_cost = sum(
        float(trade["price"])
        * float(trade["quantity"])
        * float(trade.get("slippage_bps", 0))
        / 10_000
        for trade in trades
    )

    return {
        "initial_capital": round(float(initial_capital), 2),
        "final_equity": round(final_equity, 2),
        "total_return": round(total_return, 8),
        "cagr": round(cagr, 8),
        "benchmark_return": round(benchmark_return, 8),
        "excess_return": round(total_return - benchmark_return, 8),
        "sharpe": round(sharpe, 6),
        "sortino": round(sortino, 6),
        "calmar": round(calmar, 6),
        "annualized_volatility": round(volatility, 6),
        "max_drawdown": round(max_drawdown, 8),
        "max_drawdown_duration_bars": max_drawdown_duration,
        "max_drawdown_peak": _index_date(frame.index[peak_position]),
        "max_drawdown_trough": _index_date(frame.index[trough_position]),
        "max_drawdown_recovery": (
            _index_date(frame.index[recovery_position]) if recovery_position is not None else None
        ),
        "market_exposure": round(exposure, 6),
        "win_rate": round(len(wins) / len(completed), 6) if completed else 0.0,
        "profit_factor": round(profit_factor, 6) if math.isfinite(profit_factor) else None,
        "expectancy": round(expectancy, 2),
        "average_win": round(average_win, 2),
        "average_loss": round(average_loss, 2),
        "average_trade_duration_days": (
            round(sum(durations) / len(durations), 2) if durations else 0.0
        ),
        "turnover": round(turnover, 6),
        "completed_trades": len(completed),
        "open_positions": len(open_trades),
        "trade_events": len(trades),
        "total_commission": round(sum(trade["commission"] for trade in trades), 2),
        "estimated_slippage_cost": round(slippage_cost, 2),
    }


def periodic_returns(frame: pd.DataFrame) -> dict[str, list[dict]]:
    """Return calendar-period performance derived from the equity curve."""
    if frame.empty or "equity" not in frame:
        raise ValueError("Backtest frame must include equity values")
    index = pd.DatetimeIndex(frame.index)
    equity = pd.Series(frame["equity"].astype(float).values, index=index)
    monthly = equity.resample("ME").last().ffill().pct_change(fill_method=None)
    yearly = equity.resample("YE").last().ffill().pct_change(fill_method=None)

    # The first period starts at initial equity rather than disappearing from pct_change.
    monthly.iloc[0] = equity.loc[: monthly.index[0]].iloc[-1] / equity.iloc[0] - 1
    yearly.iloc[0] = equity.loc[: yearly.index[0]].iloc[-1] / equity.iloc[0] - 1
    return {
        "monthly": [
            {"period": timestamp.strftime("%Y-%m"), "return": round(float(value), 8)}
            for timestamp, value in monthly.items()
        ],
        "yearly": [
            {"period": timestamp.strftime("%Y"), "return": round(float(value), 8)}
            for timestamp, value in yearly.items()
        ],
    }


def _index_date(value) -> str:
    return pd.Timestamp(value).isoformat()
