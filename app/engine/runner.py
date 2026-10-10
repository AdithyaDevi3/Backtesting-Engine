from dataclasses import dataclass
import math

import pandas as pd

from app.engine.strategies.base import BaseStrategy


@dataclass(frozen=True)
class BacktestResult:
    frame: pd.DataFrame
    trades: list[dict]


def run_backtest(
    data: pd.DataFrame,
    strategy: BaseStrategy,
    initial_capital: float = 10_000,
    commission: float = 0,
    slippage_bps: float = 0,
    execution_model: str = "next_open",
    position_size_pct: float = 100,
    stop_loss_pct: float | None = None,
    take_profit_pct: float | None = None,
    fractional_shares: bool = True,
) -> BacktestResult:
    """Run a deterministic, long-only, all-in backtest."""
    if initial_capital <= 0:
        raise ValueError("initial_capital must be positive")
    if commission < 0:
        raise ValueError("commission cannot be negative")

    frame = strategy.generate_signals(data.sort_index().copy())
    if execution_model == "next_open":
        return run_signals(
            frame, initial_capital, commission, slippage_bps, signal_delay=1,
            execution_price_column="open", position_size_pct=position_size_pct,
            stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct,
            fractional_shares=fractional_shares,
        )
    if execution_model == "same_close":
        return run_signals(
            frame, initial_capital, commission, slippage_bps, signal_delay=0,
            execution_price_column="close", position_size_pct=position_size_pct,
            stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct,
            fractional_shares=fractional_shares,
        )
    raise ValueError("execution_model must be 'next_open' or 'same_close'")


def run_signals(
    frame: pd.DataFrame,
    initial_capital: float = 10_000,
    commission: float = 0,
    slippage_bps: float = 0,
    signal_delay: int = 1,
    execution_price_column: str = "open",
    position_size_pct: float = 100,
    stop_loss_pct: float | None = None,
    take_profit_pct: float | None = None,
    fractional_shares: bool = True,
) -> BacktestResult:
    """Simulate a frame that already contains close prices and position signals."""
    if initial_capital <= 0:
        raise ValueError("initial_capital must be positive")
    if commission < 0:
        raise ValueError("commission cannot be negative")
    if not 0 <= slippage_bps <= 1_000:
        raise ValueError("slippage_bps must be between 0 and 1000")
    if signal_delay < 0:
        raise ValueError("signal_delay cannot be negative")
    if not 0 < position_size_pct <= 100:
        raise ValueError("position_size_pct must be greater than 0 and at most 100")
    if stop_loss_pct is not None and not 0 < stop_loss_pct < 100:
        raise ValueError("stop_loss_pct must be between 0 and 100")
    if take_profit_pct is not None and take_profit_pct <= 0:
        raise ValueError("take_profit_pct must be positive")
    if frame.empty:
        raise ValueError("Signal frame is empty")
    if not {"close", "signal"}.issubset(frame.columns):
        raise ValueError("Signal frame must include 'close' and 'signal' columns")
    if not frame.index.is_monotonic_increasing:
        raise ValueError("Signal frame index must be sorted in ascending order")
    if not frame.index.is_unique:
        raise ValueError("Signal frame index must not contain duplicate timestamps")
    if frame["close"].isna().any() or not frame["close"].map(
        lambda value: math.isfinite(float(value))
    ).all():
        raise ValueError("Signal frame close prices must be finite")
    if frame["signal"].isna().any() or not frame["signal"].isin([-1, 0, 1]).all():
        raise ValueError("Signals must contain only -1, 0, or 1")
    frame = frame.copy()
    cash = float(initial_capital)
    quantity = 0.0
    trades: list[dict] = []
    equity: list[float] = []
    positions: list[float] = []
    executable_signals = frame["signal"].shift(signal_delay).fillna(0).astype(int)
    entry_price: float | None = None

    for row_number, (timestamp, row) in enumerate(frame.iterrows()):
        mark_price = float(row["close"])
        raw_execution_price = row.get(execution_price_column, mark_price)
        raw_execution_price = mark_price if pd.isna(raw_execution_price) else float(raw_execution_price)
        bar_open = row.get("open", mark_price)
        bar_high = row.get("high", mark_price)
        bar_low = row.get("low", mark_price)
        bar_open = mark_price if pd.isna(bar_open) else float(bar_open)
        bar_high = mark_price if pd.isna(bar_high) else float(bar_high)
        bar_low = mark_price if pd.isna(bar_low) else float(bar_low)
        signal = int(executable_signals.iloc[row_number])
        if min(mark_price, raw_execution_price, bar_open, bar_high, bar_low) <= 0:
            raise ValueError(f"Invalid market price at {timestamp}")
        has_ohlc_range = {"open", "high", "low"}.issubset(frame.columns)
        if has_ohlc_range and (
            bar_low > min(bar_open, mark_price) or bar_high < max(bar_open, mark_price)
        ):
            raise ValueError(f"Inconsistent OHLC range at {timestamp}")

        exited_for_risk = False
        if quantity > 0 and entry_price is not None:
            risk_price, risk_reason = _risk_exit_price(
                entry_price,
                bar_open,
                bar_high,
                bar_low,
                stop_loss_pct,
                take_profit_pct,
            )
            if risk_price is not None:
                price = risk_price * (1 - slippage_bps / 10_000)
                cash += quantity * price - commission
                trades.append(
                    _trade(timestamp, "sell", price, quantity, commission, slippage_bps, risk_reason)
                )
                quantity = 0.0
                entry_price = None
                exited_for_risk = True

        if signal == 1 and quantity == 0 and cash > commission and not exited_for_risk:
            price = raw_execution_price * (1 + slippage_bps / 10_000)
            allocation = cash * position_size_pct / 100
            if allocation > commission:
                requested_quantity = (allocation - commission) / price
                purchase_quantity = (
                    requested_quantity if fractional_shares else math.floor(requested_quantity)
                )
                if purchase_quantity > 0:
                    quantity = purchase_quantity
                    cash -= quantity * price + commission
                    entry_price = price
                    trades.append(
                        _trade(timestamp, "buy", price, quantity, commission, slippage_bps, "signal")
                    )
        elif signal == -1 and quantity > 0:
            price = raw_execution_price * (1 - slippage_bps / 10_000)
            cash += quantity * price - commission
            trades.append(_trade(timestamp, "sell", price, quantity, commission, slippage_bps, "signal"))
            quantity = 0.0
            entry_price = None

        positions.append(quantity)
        equity.append(cash + quantity * mark_price)

    frame["position"] = positions
    frame["equity"] = equity
    frame["returns"] = frame["equity"].pct_change().fillna(0.0)
    frame["drawdown"] = frame["equity"] / frame["equity"].cummax() - 1
    return BacktestResult(frame=frame, trades=trades)


def _trade(
    timestamp,
    side: str,
    price: float,
    quantity: float,
    commission: float,
    slippage_bps: float,
    reason: str,
) -> dict:
    parsed = pd.Timestamp(timestamp)
    return {
        "date": parsed.isoformat(),
        "type": side,
        "price": round(price, 6),
        "quantity": round(quantity, 8),
        "commission": round(commission, 6),
        "slippage_bps": round(slippage_bps, 4),
        "reason": reason,
    }


def _risk_exit_price(
    entry_price: float,
    bar_open: float,
    bar_high: float,
    bar_low: float,
    stop_loss_pct: float | None,
    take_profit_pct: float | None,
) -> tuple[float | None, str]:
    if stop_loss_pct is not None:
        stop_price = entry_price * (1 - stop_loss_pct / 100)
        if bar_open <= stop_price:
            return bar_open, "stop_loss"
        if bar_low <= stop_price:
            return stop_price, "stop_loss"
    if take_profit_pct is not None:
        target_price = entry_price * (1 + take_profit_pct / 100)
        if bar_open >= target_price:
            return bar_open, "take_profit"
        if bar_high >= target_price:
            return target_price, "take_profit"
    return None, ""
