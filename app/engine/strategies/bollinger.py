import pandas as pd

from app.engine.strategies.base import BaseStrategy


class BollingerBandsStrategy(BaseStrategy):
    name = "bollinger"

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        self._validate_prices(data)
        window = int(self.params.get("window", 20))
        standard_deviations = float(self.params.get("standard_deviations", 2))
        if window < 2:
            raise ValueError("Bollinger window must be at least 2")
        if standard_deviations <= 0:
            raise ValueError("standard_deviations must be positive")

        result = data.copy()
        result["bollinger_middle"] = result["close"].rolling(window).mean()
        rolling_std = result["close"].rolling(window).std(ddof=0)
        result["bollinger_upper"] = result["bollinger_middle"] + standard_deviations * rolling_std
        result["bollinger_lower"] = result["bollinger_middle"] - standard_deviations * rolling_std

        regime = pd.Series(float("nan"), index=result.index)
        regime.loc[result["close"] < result["bollinger_lower"]] = 1
        regime.loc[result["close"] > result["bollinger_upper"]] = -1
        result["signal"] = regime.ffill().fillna(0).astype(int)
        return result
