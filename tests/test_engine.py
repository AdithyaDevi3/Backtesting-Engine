import pandas as pd
import pytest

from app.engine import (
    PortfolioComponentResult,
    combine_portfolio,
    compute_metrics,
    periodic_returns,
    run_backtest,
    run_signals,
)
from app.engine.strategies import (
    BollingerBandsStrategy,
    MACDStrategy,
    RSIStrategy,
    SMACrossover,
    get_strategy,
)
from app.engine.walk_forward import run_walk_forward


def prices(values: list[float]) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=len(values), freq="D")
    return pd.DataFrame({"close": values}, index=index)


def test_sma_backtest_builds_equity_curve_and_trade_log():
    result = run_backtest(
        prices([10, 11, 12, 13, 12, 11, 10]),
        SMACrossover({"short_window": 2, "long_window": 3}),
        initial_capital=1_000,
        commission=1,
    )

    assert result.frame["equity"].notna().all()
    assert [trade["type"] for trade in result.trades] == ["buy", "sell"]
    metrics = compute_metrics(result.frame, result.trades, 1_000)
    assert metrics["trade_events"] == 2
    assert metrics["completed_trades"] == 1
    assert metrics["max_drawdown"] <= 0


def test_rsi_strategy_generates_entry_and_exit_regimes():
    frame = RSIStrategy({"period": 2, "oversold": 35, "overbought": 65}).generate_signals(
        prices([10, 9, 8, 7, 8, 9, 10, 11])
    )

    assert 1 in frame["signal"].values
    assert -1 in frame["signal"].values


def test_macd_strategy_generates_both_market_regimes():
    values = list(range(100, 150)) + list(range(150, 90, -1))
    frame = MACDStrategy({"fast_period": 3, "slow_period": 6, "signal_period": 3}).generate_signals(
        prices(values)
    )

    assert 1 in frame["signal"].values
    assert -1 in frame["signal"].values
    assert frame["macd_histogram"].notna().any()


def test_bollinger_strategy_enters_and_exits_at_outer_bands():
    values = [10.0] * 20 + [5.0] + [10.0] * 20 + [15.0]
    frame = BollingerBandsStrategy({"window": 20, "standard_deviations": 2}).generate_signals(
        prices(values)
    )

    assert 1 in frame["signal"].values
    assert -1 in frame["signal"].values


def test_strategy_factory_rejects_unknown_strategy():
    with pytest.raises(ValueError, match="Unknown strategy"):
        get_strategy("momentum")


def test_sma_rejects_inverted_windows():
    with pytest.raises(ValueError, match="short_window"):
        SMACrossover({"short_window": 50, "long_window": 20}).generate_signals(prices([1, 2, 3]))


def test_walk_forward_selects_parameters_without_trading_on_training_rows():
    values = [100 + index * 0.2 + (index % 10) for index in range(100)]
    result = run_walk_forward(
        prices(values),
        "sma",
        {"short_window": [3, 5], "long_window": [10, 15]},
        train_points=40,
        test_points=20,
        initial_capital=1_000,
    )

    assert result["fold_count"] == 3
    assert result["final_equity"] > 0
    assert result["folds"][0]["test_start"] > result["folds"][0]["train_end"]
    assert result["folds"][0]["params"]["short_window"] in {3, 5}


def test_metrics_include_benchmark_and_risk_adjusted_returns():
    result = run_backtest(
        prices([10, 11, 12, 11, 13, 14]),
        SMACrossover({"short_window": 2, "long_window": 3}),
        initial_capital=1_000,
    )
    metrics = compute_metrics(result.frame, result.trades, 1_000)

    assert {
        "cagr",
        "benchmark_return",
        "excess_return",
        "sortino",
        "calmar",
        "turnover",
        "expectancy",
        "max_drawdown_duration_bars",
    } <= metrics.keys()


def test_metrics_match_hand_calculated_trade_and_drawdown_statistics():
    index = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"])
    frame = pd.DataFrame(
        {
            "close": [10.0, 12.0, 9.0, 11.0],
            "equity": [1_000.0, 1_200.0, 900.0, 1_100.0],
            "position": [0.0, 10.0, 10.0, 0.0],
        },
        index=index,
    )
    trades = [
        {
            "date": index[0].isoformat(),
            "type": "buy",
            "price": 10,
            "quantity": 10,
            "commission": 1,
            "slippage_bps": 5,
        },
        {
            "date": index[3].isoformat(),
            "type": "sell",
            "price": 11,
            "quantity": 10,
            "commission": 1,
            "slippage_bps": 5,
        },
    ]

    metrics = compute_metrics(frame, trades, 1_000)

    assert metrics["max_drawdown"] == pytest.approx(-0.25)
    assert metrics["max_drawdown_duration_bars"] == 2
    assert metrics["expectancy"] == pytest.approx(8)
    assert metrics["average_trade_duration_days"] == pytest.approx(3)
    assert metrics["open_positions"] == 0


def test_periodic_returns_include_first_partial_month_and_year():
    index = pd.to_datetime(["2024-01-02", "2024-01-31", "2024-02-29", "2025-01-02"])
    frame = pd.DataFrame({"equity": [100.0, 110.0, 121.0, 133.1]}, index=index)

    periods = periodic_returns(frame)

    assert periods["monthly"][0] == {"period": "2024-01", "return": pytest.approx(0.1)}
    assert periods["monthly"][1] == {"period": "2024-02", "return": pytest.approx(0.1)}
    assert periods["yearly"][0] == {"period": "2024", "return": pytest.approx(0.21)}


def test_signal_runner_rejects_duplicate_or_unsorted_timestamps():
    duplicate = pd.DataFrame(
        {"close": [10.0, 11.0], "signal": [0, 1]},
        index=pd.to_datetime(["2024-01-01", "2024-01-01"]),
    )
    unsorted = pd.DataFrame(
        {"close": [11.0, 10.0], "signal": [0, 1]},
        index=pd.to_datetime(["2024-01-02", "2024-01-01"]),
    )

    with pytest.raises(ValueError, match="duplicate"):
        run_signals(duplicate)
    with pytest.raises(ValueError, match="sorted"):
        run_signals(unsorted)


def test_signal_runner_rejects_invalid_signals_and_ohlc_ranges():
    invalid_signal = pd.DataFrame(
        {"close": [10.0], "signal": [0.5]}, index=pd.to_datetime(["2024-01-01"])
    )
    invalid_range = pd.DataFrame(
        {"open": [10.0], "high": [9.0], "low": [8.0], "close": [10.0], "signal": [0]},
        index=pd.to_datetime(["2024-01-01"]),
    )

    with pytest.raises(ValueError, match="Signals"):
        run_signals(invalid_signal)
    with pytest.raises(ValueError, match="OHLC"):
        run_signals(invalid_range)


def test_next_open_execution_delays_signals_and_applies_adverse_slippage():
    index = pd.date_range("2024-01-01", periods=3, freq="D")
    frame = pd.DataFrame(
        {
            "open": [100.0, 110.0, 120.0],
            "close": [105.0, 115.0, 125.0],
            "signal": [1, -1, 0],
        },
        index=index,
    )

    result = run_signals(
        frame,
        initial_capital=1_000,
        slippage_bps=100,
        signal_delay=1,
        execution_price_column="open",
    )

    assert [trade["date"] for trade in result.trades] == [index[1].isoformat(), index[2].isoformat()]
    assert result.trades[0]["price"] == pytest.approx(111.1)
    assert result.trades[1]["price"] == pytest.approx(118.8)
    frictionless = run_signals(
        frame,
        initial_capital=1_000,
        signal_delay=1,
        execution_price_column="open",
    )
    assert result.frame["equity"].iloc[-1] < frictionless.frame["equity"].iloc[-1]


def test_position_sizing_and_conservative_risk_exit():
    index = pd.date_range("2024-01-01", periods=2, freq="D")
    frame = pd.DataFrame(
        {
            "open": [100.0, 100.0],
            "high": [101.0, 120.0],
            "low": [99.0, 90.0],
            "close": [100.0, 100.0],
            "signal": [1, 1],
        },
        index=index,
    )

    result = run_signals(
        frame,
        initial_capital=1_000,
        signal_delay=0,
        execution_price_column="open",
        position_size_pct=50,
        stop_loss_pct=5,
        take_profit_pct=10,
    )

    assert result.trades[0]["quantity"] == pytest.approx(5)
    assert result.trades[1]["reason"] == "stop_loss"
    assert result.trades[1]["price"] == pytest.approx(95)
    assert result.frame["equity"].iloc[-1] == pytest.approx(975)


def test_whole_share_execution_preserves_uninvested_cash():
    frame = pd.DataFrame(
        {"open": [30.0, 33.0], "close": [30.0, 33.0], "signal": [1, -1]},
        index=pd.date_range("2024-01-01", periods=2, freq="D"),
    )

    result = run_signals(
        frame,
        initial_capital=100,
        signal_delay=0,
        execution_price_column="open",
        fractional_shares=False,
    )

    assert result.trades[0]["quantity"] == 3
    assert result.frame["equity"].iloc[0] == pytest.approx(100)
    assert result.frame["equity"].iloc[-1] == pytest.approx(109)


def test_portfolio_combines_allocations_and_attributes_components():
    first = run_backtest(
        prices([10, 11, 12, 13, 12, 11, 10]),
        SMACrossover({"short_window": 2, "long_window": 3}),
        initial_capital=600,
    )
    second = run_backtest(
        prices([20, 19, 18, 19, 20, 21, 22]),
        RSIStrategy({"period": 2, "oversold": 40, "overbought": 60}),
        initial_capital=400,
    )

    portfolio = combine_portfolio(
        [
            PortfolioComponentResult("AAA", "sma", 600, first),
            PortfolioComponentResult("BBB", "rsi", 400, second),
        ],
        initial_capital=1_000,
    )

    assert portfolio["frame"]["equity"].iloc[0] == pytest.approx(1_000)
    assert len(portfolio["components"]) == 2
    assert {trade["ticker"] for trade in portfolio["trades"]} <= {"AAA", "BBB"}
    assert portfolio["metrics"]["initial_capital"] == 1_000
