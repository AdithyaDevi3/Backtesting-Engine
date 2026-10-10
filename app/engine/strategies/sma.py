import pandas as pd

from app.engine.strategies.base import BaseStrategy


class SMACrossover(BaseStrategy):
    name = "sma"

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        self._validate_prices(data)
        short_window = int(self.params.get("short_window", 20))
        long_window = int(self.params.get("long_window", 50))
        if short_window < 1 or long_window < 2:
            raise ValueError("SMA windows must be positive")
        if short_window >= long_window:
            raise ValueError("short_window must be smaller than long_window")

        result = data.copy()
        result["sma_short"] = result["close"].rolling(short_window).mean()
        result["sma_long"] = result["close"].rolling(long_window).mean()
        result["signal"] = 0
        ready = result["sma_long"].notna()
        result.loc[ready & (result["sma_short"] > result["sma_long"]), "signal"] = 1
        result.loc[ready & (result["sma_short"] <= result["sma_long"]), "signal"] = -1
        return result
