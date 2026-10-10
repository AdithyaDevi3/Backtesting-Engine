from datetime import date, timedelta
import os

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st


st.set_page_config(page_title="AlphaTest", page_icon="📈", layout="wide")
st.title("AlphaTest Strategy Backtester")
st.caption("Compare systematic trading ideas against historical OHLCV data.")

STRATEGY_DEFAULTS = {
    "sma": {"short_window": 20, "long_window": 50},
    "rsi": {"period": 14, "overbought": 70, "oversold": 30},
    "macd": {"fast_period": 12, "slow_period": 26, "signal_period": 9},
    "bollinger": {"window": 20, "standard_deviations": 2},
}

with st.sidebar:
    st.header("Configuration")
    api_url = st.text_input("API URL", os.getenv("ALPHATEST_API_URL", "http://localhost:8000"))
    api_key = st.text_input(
        "API key (optional)", value=os.getenv("ALPHATEST_API_KEY", ""), type="password"
    )
    ticker = st.text_input("Ticker", "AAPL").upper()
    strategy = st.selectbox("Strategy", ["sma", "rsi", "macd", "bollinger"])
    start = st.date_input("Start date", date.today() - timedelta(days=365 * 5))
    end = st.date_input("End date", date.today())
    capital = st.number_input("Initial capital", min_value=100.0, value=10_000.0, step=1_000.0)
    commission = st.number_input("Commission per trade", min_value=0.0, value=0.0, step=0.5)
    slippage_bps = st.number_input(
        "Slippage (basis points)", min_value=0.0, max_value=1_000.0, value=0.0, step=1.0
    )
    execution_model = st.selectbox(
        "Execution model",
        ["next_open", "same_close"],
        help="Next open avoids trading on the same close used to calculate a signal.",
    )
    position_size_pct = st.slider("Position size (%)", 5, 100, 100, 5)
    fractional_shares = st.checkbox("Allow fractional shares", value=True)
    use_stop_loss = st.checkbox("Use stop loss")
    stop_loss_pct = (
        st.number_input("Stop loss (%)", min_value=0.1, max_value=99.9, value=10.0, step=0.5)
        if use_stop_loss
        else None
    )
    use_take_profit = st.checkbox("Use take profit")
    take_profit_pct = (
        st.number_input("Take profit (%)", min_value=0.1, value=20.0, step=0.5)
        if use_take_profit
        else None
    )
    if strategy == "sma":
        short_window = st.slider("Short window", 2, 100, 20)
        long_window = st.slider("Long window", 5, 250, 50)
        params = {"short_window": short_window, "long_window": long_window}
    elif strategy == "rsi":
        period = st.slider("RSI period", 2, 50, 14)
        overbought = st.slider("Overbought", 51, 95, 70)
        oversold = st.slider("Oversold", 5, 49, 30)
        params = {"period": period, "overbought": overbought, "oversold": oversold}
    elif strategy == "macd":
        fast_period = st.slider("Fast EMA", 2, 30, 12)
        slow_period = st.slider("Slow EMA", 5, 60, 26)
        signal_period = st.slider("Signal EMA", 2, 30, 9)
        params = {
            "fast_period": fast_period,
            "slow_period": slow_period,
            "signal_period": signal_period,
        }
    else:
        band_window = st.slider("Band window", 5, 100, 20)
        standard_deviations = st.slider("Standard deviations", 0.5, 4.0, 2.0, 0.1)
        params = {"window": band_window, "standard_deviations": standard_deviations}
    run = st.button("Run backtest", type="primary", use_container_width=True)
    compare = st.button("Compare all strategies", use_container_width=True)
    walk_forward = st.button("Run walk-forward", use_container_width=True)
    load_history = st.button("Load result history", use_container_width=True)
    show_configurations = st.checkbox("Manage saved configurations")
    with st.expander("Save current configuration"):
        configuration_name = st.text_input("Configuration name")
        configuration_description = st.text_area("Description", height=80)
        save_configuration = st.button("Save configuration", use_container_width=True)
    with st.expander("Two-asset portfolio lab"):
        second_ticker = st.text_input("Second ticker", "MSFT").upper()
        primary_allocation = st.slider("Primary allocation (%)", 5, 95, 60, 5)
        second_strategy = st.selectbox(
            "Second strategy",
            list(STRATEGY_DEFAULTS),
            index=0,
            key="portfolio_second_strategy",
        )
        run_portfolio = st.button("Run portfolio", use_container_width=True)

request_headers = {"X-API-Key": api_key} if api_key else {}
current_payload = {
    "ticker": ticker,
    "strategy": strategy,
    "params": params,
    "start_date": start.isoformat(),
    "end_date": end.isoformat(),
    "initial_capital": capital,
    "commission": commission,
    "slippage_bps": slippage_bps,
    "execution_model": execution_model,
    "position_size_pct": position_size_pct,
    "stop_loss_pct": stop_loss_pct,
    "take_profit_pct": take_profit_pct,
    "fractional_shares": fractional_shares,
}

if save_configuration:
    if not configuration_name.strip():
        st.sidebar.error("Enter a configuration name before saving.")
    else:
        try:
            save_response = requests.post(
                f"{api_url.rstrip('/')}/api/configurations",
                json={
                    **current_payload,
                    "name": configuration_name,
                    "description": configuration_description or None,
                },
                headers=request_headers,
                timeout=30,
            )
            save_response.raise_for_status()
        except requests.RequestException as exc:
            detail = save_response.text if "save_response" in locals() else str(exc)
            st.sidebar.error(f"Could not save configuration: {detail}")
        else:
            st.sidebar.success(f"Saved {save_response.json()['name']}.")

if show_configurations:
    st.subheader("Saved configurations")
    try:
        configurations_response = requests.get(
            f"{api_url.rstrip('/')}/api/configurations",
            headers=request_headers,
            timeout=30,
        )
        configurations_response.raise_for_status()
    except requests.RequestException as exc:
        st.error(f"Could not load saved configurations: {exc}")
    else:
        configurations = configurations_response.json()
        if configurations:
            selected_configuration = st.selectbox(
                "Configuration",
                configurations,
                format_func=lambda item: (
                    f"{item['name']} · {item['ticker']} · {item['strategy'].upper()}"
                ),
            )
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "name": item["name"],
                            "ticker": item["ticker"],
                            "strategy": item["strategy"],
                            "dates": f"{item['start_date']} to {item['end_date']}",
                            "capital": item["initial_capital"],
                            "updated_at": item["updated_at"],
                        }
                        for item in configurations
                    ]
                ),
                use_container_width=True,
                hide_index=True,
            )
            run_saved, delete_saved = st.columns(2)
            if run_saved.button("Run selected configuration", use_container_width=True):
                try:
                    configured_response = requests.post(
                        f"{api_url.rstrip('/')}/api/configurations/{selected_configuration['id']}/run",
                        headers=request_headers,
                        timeout=60,
                    )
                    configured_response.raise_for_status()
                except requests.RequestException as exc:
                    st.error(f"Saved configuration failed: {exc}")
                else:
                    st.session_state["queued_backtest_result"] = configured_response.json()
                    st.rerun()
            if delete_saved.button("Delete selected configuration", use_container_width=True):
                try:
                    delete_response = requests.delete(
                        f"{api_url.rstrip('/')}/api/configurations/{selected_configuration['id']}",
                        headers=request_headers,
                        timeout=30,
                    )
                    delete_response.raise_for_status()
                except requests.RequestException as exc:
                    st.error(f"Could not delete configuration: {exc}")
                else:
                    st.rerun()
        else:
            st.info("No saved configurations yet.")

queued_result = st.session_state.pop("queued_backtest_result", None)
if run:
    try:
        backtest_response = requests.post(
            f"{api_url.rstrip('/')}/api/backtest",
            json=current_payload,
            headers=request_headers,
            timeout=60,
        )
        backtest_response.raise_for_status()
    except requests.RequestException as exc:
        detail = backtest_response.text if "backtest_response" in locals() else str(exc)
        st.error(f"Backtest request failed: {detail}")
        st.stop()
    queued_result = backtest_response.json()

if queued_result is not None:
    data = queued_result
    display_capital = data["metrics"]["initial_capital"]
    display_ticker = data["ticker"]
    display_strategy = data["strategy"]
    metrics = data["metrics"]
    columns = st.columns(5)
    columns[0].metric("Total return", f"{metrics['total_return']:.2%}")
    columns[1].metric("Final equity", f"${metrics['final_equity']:,.2f}")
    columns[2].metric("Sharpe ratio", f"{metrics['sharpe']:.2f}")
    columns[3].metric("Max drawdown", f"{metrics['max_drawdown']:.2%}")
    columns[4].metric("Win rate", f"{metrics['win_rate']:.2%}")

    equity = pd.DataFrame(data["equity_curve"])
    equity["date"] = pd.to_datetime(equity["date"])
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=equity["date"], y=equity["equity"], name="Portfolio"))
    benchmark = display_capital * equity["close"] / equity["close"].iloc[0]
    figure.add_trace(
        go.Scatter(
            x=equity["date"], y=benchmark, name="Buy and hold", line={"dash": "dash"}
        )
    )
    figure.update_layout(
        title=f"{display_ticker} equity curve", xaxis_title="Date", yaxis_title="Equity"
    )
    st.plotly_chart(figure, use_container_width=True)
    drawdown_figure = go.Figure(
        go.Scatter(
            x=equity["date"],
            y=equity["drawdown"],
            fill="tozeroy",
            name="Drawdown",
            line={"color": "#d62728"},
        )
    )
    drawdown_figure.update_layout(
        title="Drawdown from prior equity peak", xaxis_title="Date", yaxis_tickformat=".1%"
    )
    st.plotly_chart(drawdown_figure, use_container_width=True)
    st.download_button(
        "Download equity CSV",
        equity.to_csv(index=False).encode("utf-8"),
        file_name=f"{display_ticker}_{display_strategy}_equity.csv",
        mime="text/csv",
    )

    left, right = st.columns([2, 1])
    with left:
        st.subheader("Trade history")
        if data["trades"]:
            trades_frame = pd.DataFrame(data["trades"])
            st.dataframe(trades_frame, use_container_width=True, hide_index=True)
            st.download_button(
                "Download trades CSV",
                trades_frame.to_csv(index=False).encode("utf-8"),
                file_name=f"{display_ticker}_{display_strategy}_trades.csv",
                mime="text/csv",
            )
        else:
            st.info("This configuration produced no trades.")
    with right:
        st.subheader("Performance breakdown")
        st.dataframe(
            pd.DataFrame({"Metric": list(metrics), "Value": list(metrics.values())}),
            use_container_width=True,
            hide_index=True,
        )

    provenance = data["provenance"]
    with st.expander("Experiment provenance"):
        st.caption(
            "Use these identifiers to verify the exact code, request, "
            "and OHLCV input behind this result."
        )
        st.dataframe(
            pd.DataFrame(
                [
                    {"Field": "Engine revision", "Value": provenance["engine_revision"]},
                    {"Field": "Request fingerprint", "Value": provenance["request_fingerprint"]},
                    {"Field": "Data fingerprint", "Value": provenance["data_fingerprint"]},
                    {"Field": "Input rows", "Value": provenance["data_row_count"]},
                    {"Field": "Input start", "Value": provenance["data_start"]},
                    {"Field": "Input end", "Value": provenance["data_end"]},
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Calendar returns")
    periodic = data["periodic_returns"]
    calendar_left, calendar_right = st.columns(2)
    with calendar_left:
        monthly = pd.DataFrame(periodic["monthly"])
        if not monthly.empty:
            monthly["return"] = monthly["return"].map(lambda value: f"{value:.2%}")
        st.caption("Monthly")
        st.dataframe(monthly, use_container_width=True, hide_index=True)
    with calendar_right:
        yearly = pd.DataFrame(periodic["yearly"])
        if not yearly.empty:
            yearly["return"] = yearly["return"].map(lambda value: f"{value:.2%}")
        st.caption("Yearly")
        st.dataframe(yearly, use_container_width=True, hide_index=True)
else:
    st.info("Choose a strategy and run a backtest to view results.")

if compare:
    request_headers = {"X-API-Key": api_key} if api_key else {}
    comparison_payload = {
        "ticker": ticker,
        "strategies": [
            {"strategy": "sma", "params": {"short_window": 20, "long_window": 50}},
            {"strategy": "rsi", "params": {"period": 14, "overbought": 70, "oversold": 30}},
            {
                "strategy": "macd",
                "params": {"fast_period": 12, "slow_period": 26, "signal_period": 9},
            },
            {"strategy": "bollinger", "params": {"window": 20, "standard_deviations": 2}},
        ],
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "initial_capital": capital,
        "commission": commission,
        "slippage_bps": slippage_bps,
        "execution_model": execution_model,
        "position_size_pct": position_size_pct,
        "stop_loss_pct": stop_loss_pct,
        "take_profit_pct": take_profit_pct,
        "fractional_shares": fractional_shares,
    }
    try:
        comparison_response = requests.post(
            f"{api_url.rstrip('/')}/api/compare",
            json=comparison_payload,
            headers=request_headers,
            timeout=60,
        )
        comparison_response.raise_for_status()
    except requests.RequestException as exc:
        st.error(f"Comparison failed: {exc}")
    else:
        comparison = comparison_response.json()["results"]
        comparison_chart = go.Figure()
        summary_rows = []
        for result in comparison:
            curve = pd.DataFrame(result["equity_curve"])
            comparison_chart.add_trace(
                go.Scatter(
                    x=pd.to_datetime(curve["date"]),
                    y=curve["equity"],
                    name=result["strategy"].upper(),
                )
            )
            summary_rows.append({"strategy": result["strategy"], **result["metrics"]})
        comparison_chart.update_layout(
            title=f"{ticker} strategy comparison", xaxis_title="Date", yaxis_title="Equity"
        )
        st.plotly_chart(comparison_chart, use_container_width=True)
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

if walk_forward:
    request_headers = {"X-API-Key": api_key} if api_key else {}
    grids = {
        "sma": {"short_window": [10, 20], "long_window": [50, 100]},
        "rsi": {"period": [7, 14], "overbought": [70], "oversold": [30]},
        "macd": {"fast_period": [8, 12], "slow_period": [20, 26], "signal_period": [9]},
        "bollinger": {"window": [15, 20], "standard_deviations": [1.5, 2]},
    }
    walk_forward_payload = {
        "ticker": ticker,
        "strategy": strategy,
        "parameter_grid": grids[strategy],
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "initial_capital": capital,
        "commission": commission,
        "slippage_bps": slippage_bps,
        "execution_model": execution_model,
        "position_size_pct": position_size_pct,
        "stop_loss_pct": stop_loss_pct,
        "take_profit_pct": take_profit_pct,
        "fractional_shares": fractional_shares,
        "train_points": 252,
        "test_points": 63,
    }
    try:
        walk_forward_response = requests.post(
            f"{api_url.rstrip('/')}/api/walk-forward",
            json=walk_forward_payload,
            headers=request_headers,
            timeout=120,
        )
        walk_forward_response.raise_for_status()
    except requests.RequestException as exc:
        st.error(f"Walk-forward analysis failed: {exc}")
    else:
        analysis = walk_forward_response.json()
        st.subheader("Walk-forward out-of-sample results")
        summary = st.columns(3)
        summary[0].metric("Out-of-sample return", f"{analysis['total_return']:.2%}")
        summary[1].metric("Final equity", f"${analysis['final_equity']:,.2f}")
        summary[2].metric("Folds", analysis["fold_count"])
        fold_rows = [
            {
                "test_start": fold["test_start"],
                "test_end": fold["test_end"],
                "selected_params": fold["params"],
                "test_return": fold["test_metrics"]["total_return"],
                "test_sharpe": fold["test_metrics"]["sharpe"],
                "test_drawdown": fold["test_metrics"]["max_drawdown"],
            }
            for fold in analysis["folds"]
        ]
        st.dataframe(pd.DataFrame(fold_rows), use_container_width=True, hide_index=True)

if run_portfolio:
    request_headers = {"X-API-Key": api_key} if api_key else {}
    portfolio_payload = {
        "components": [
            {
                "ticker": ticker,
                "allocation_pct": primary_allocation,
                "strategy": strategy,
                "params": params,
            },
            {
                "ticker": second_ticker,
                "allocation_pct": 100 - primary_allocation,
                "strategy": second_strategy,
                "params": STRATEGY_DEFAULTS[second_strategy],
            },
        ],
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "initial_capital": capital,
        "commission": commission,
        "slippage_bps": slippage_bps,
        "execution_model": execution_model,
        "position_size_pct": position_size_pct,
        "stop_loss_pct": stop_loss_pct,
        "take_profit_pct": take_profit_pct,
        "fractional_shares": fractional_shares,
    }
    try:
        portfolio_response = requests.post(
            f"{api_url.rstrip('/')}/api/portfolio",
            json=portfolio_payload,
            headers=request_headers,
            timeout=120,
        )
        portfolio_response.raise_for_status()
    except requests.RequestException as exc:
        st.error(f"Portfolio analysis failed: {exc}")
    else:
        portfolio = portfolio_response.json()
        st.subheader(f"Portfolio: {ticker} / {second_ticker}")
        portfolio_metrics = portfolio["metrics"]
        portfolio_cards = st.columns(4)
        portfolio_cards[0].metric("Total return", f"{portfolio_metrics['total_return']:.2%}")
        portfolio_cards[1].metric("Final equity", f"${portfolio_metrics['final_equity']:,.2f}")
        portfolio_cards[2].metric("Sharpe", f"{portfolio_metrics['sharpe']:.2f}")
        portfolio_cards[3].metric("Max drawdown", f"{portfolio_metrics['max_drawdown']:.2%}")

        portfolio_curve = pd.DataFrame(portfolio["equity_curve"])
        portfolio_curve["date"] = pd.to_datetime(portfolio_curve["date"])
        portfolio_figure = go.Figure()
        portfolio_figure.add_trace(
            go.Scatter(x=portfolio_curve["date"], y=portfolio_curve["equity"], name="Portfolio")
        )
        portfolio_figure.add_trace(
            go.Scatter(
                x=portfolio_curve["date"],
                y=portfolio_curve["benchmark"],
                name="Weighted buy and hold",
                line={"dash": "dash"},
            )
        )
        portfolio_figure.update_layout(xaxis_title="Date", yaxis_title="Equity")
        st.plotly_chart(portfolio_figure, use_container_width=True)
        st.dataframe(pd.DataFrame(portfolio["components"]), use_container_width=True, hide_index=True)
        portfolio_trades = pd.DataFrame(portfolio["trades"])
        st.dataframe(portfolio_trades, use_container_width=True, hide_index=True)
        download_left, download_right = st.columns(2)
        download_left.download_button(
            "Download portfolio equity",
            portfolio_curve.to_csv(index=False).encode("utf-8"),
            file_name=f"{ticker}_{second_ticker}_portfolio_equity.csv",
            mime="text/csv",
        )
        download_right.download_button(
            "Download portfolio trades",
            portfolio_trades.to_csv(index=False).encode("utf-8"),
            file_name=f"{ticker}_{second_ticker}_portfolio_trades.csv",
            mime="text/csv",
        )

if load_history:
    request_headers = {"X-API-Key": api_key} if api_key else {}
    try:
        history_response = requests.get(
            f"{api_url.rstrip('/')}/api/results", headers=request_headers, timeout=30
        )
        history_response.raise_for_status()
    except requests.RequestException as exc:
        st.error(f"Could not load result history: {exc}")
    else:
        history = history_response.json()
        st.subheader("Saved backtests")
        if history:
            history_rows = [
                {
                    "id": item["id"],
                    "created_at": item["created_at"],
                    "ticker": item["ticker"],
                    "strategy": item["strategy"],
                    "status": item["status"],
                    "execution": item["execution_model"],
                    "commission": item["commission"],
                    "slippage_bps": item["slippage_bps"],
                    "position_size_pct": item["position_size_pct"],
                    "stop_loss_pct": item["stop_loss_pct"],
                    "take_profit_pct": item["take_profit_pct"],
                    "fractional_shares": item["fractional_shares"],
                    "engine_revision": item["engine_revision"],
                    "data_rows": item["data_row_count"],
                    "data_start": item["data_start"],
                    "data_end": item["data_end"],
                    "request_fingerprint": item["request_fingerprint"],
                    "data_fingerprint": item["data_fingerprint"],
                    "total_return": item["metrics"].get("total_return"),
                    "sharpe": item["metrics"].get("sharpe"),
                    "max_drawdown": item["metrics"].get("max_drawdown"),
                }
                for item in history
            ]
            st.dataframe(pd.DataFrame(history_rows), use_container_width=True, hide_index=True)
            selected_result_id = st.selectbox(
                "Result to rerun",
                [item["id"] for item in history],
                format_func=lambda result_id: f"Result {result_id}",
            )
            if st.button("Rerun selected result", use_container_width=True):
                try:
                    rerun_response = requests.post(
                        f"{api_url.rstrip('/')}/api/results/{selected_result_id}/rerun",
                        headers=request_headers,
                        timeout=60,
                    )
                    rerun_response.raise_for_status()
                except requests.RequestException as exc:
                    detail = rerun_response.text if "rerun_response" in locals() else str(exc)
                    st.error(f"Could not rerun result: {detail}")
                else:
                    st.session_state["queued_backtest_result"] = rerun_response.json()
                    st.rerun()
        else:
            st.info("No saved backtests yet.")
