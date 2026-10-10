import pandas as pd

from app.engine.strategies.base import BaseStrategy


class MACDStrategy(BaseStrategy):
    name = "macd"

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        self._validate_prices(data)
        fast_period = int(self.params.get("fast_period", 12))
        slow_period = int(self.params.get("slow_period", 26))
        signal_period = int(self.params.get("signal_period", 9))
        if min(fast_period, slow_period, signal_period) < 1:
            raise ValueError("MACD periods must be positive")
        if fast_period >= slow_period:
            raise ValueError("fast_period must be smaller than slow_period")

        result = data.copy()
        fast_ema = result["close"].ewm(span=fast_period, min_periods=fast_period, adjust=False).mean()
        slow_ema = result["close"].ewm(span=slow_period, min_periods=slow_period, adjust=False).mean()
        result["macd"] = fast_ema - slow_ema
        result["macd_signal"] = result["macd"].ewm(
            span=signal_period, min_periods=signal_period, adjust=False
        ).mean()
        result["macd_histogram"] = result["macd"] - result["macd_signal"]
        result["signal"] = 0
        ready = result["macd_signal"].notna()
        result.loc[ready & (result["macd_histogram"] > 0), "signal"] = 1
        result.loc[ready & (result["macd_histogram"] <= 0), "signal"] = -1
        return result
