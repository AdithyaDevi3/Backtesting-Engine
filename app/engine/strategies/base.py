from abc import ABC, abstractmethod

import pandas as pd


class BaseStrategy(ABC):
    """A strategy that converts OHLCV rows into desired position signals."""

    name: str

    def __init__(self, params: dict):
        self.params = params

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Return a copy of data with a signal column (1=long, -1=flat)."""

    @staticmethod
    def _validate_prices(data: pd.DataFrame) -> None:
        if data.empty:
            raise ValueError("Price data is empty")
        if "close" not in data.columns:
            raise ValueError("Price data must include a 'close' column")
        if data["close"].isna().all():
            raise ValueError("Price data has no valid close prices")
