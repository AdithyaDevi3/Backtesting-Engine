import pandas as pd

from app.engine.strategies.base import BaseStrategy


class RSIStrategy(BaseStrategy):
    name = "rsi"

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        self._validate_prices(data)
        period = int(self.params.get("period", 14))
        overbought = float(self.params.get("overbought", 70))
        oversold = float(self.params.get("oversold", 30))
        if period < 2:
            raise ValueError("RSI period must be at least 2")
        if not 0 < oversold < overbought < 100:
            raise ValueError("RSI thresholds must satisfy 0 < oversold < overbought < 100")

        result = data.copy()
        delta = result["close"].diff()
        gain = delta.clip(lower=0).ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        relative_strength = gain / loss.replace(0, float("nan"))
        result["rsi"] = 100 - (100 / (1 + relative_strength))
        result.loc[(loss == 0) & (gain > 0), "rsi"] = 100
        result.loc[(gain == 0) & (loss > 0), "rsi"] = 0

        # Signals describe the desired position. Values between thresholds carry
        # forward the prior regime, avoiding repeated buys and sells.
        regime = pd.Series(float("nan"), index=result.index)
        regime.loc[result["rsi"] < oversold] = 1
        regime.loc[result["rsi"] > overbought] = -1
        result["signal"] = regime.ffill().fillna(0).astype(int)
        return result
