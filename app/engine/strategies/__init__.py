from app.engine.strategies.base import BaseStrategy
from app.engine.strategies.bollinger import BollingerBandsStrategy
from app.engine.strategies.macd import MACDStrategy
from app.engine.strategies.rsi import RSIStrategy
from app.engine.strategies.sma import SMACrossover


def get_strategy(name: str, params: dict | None = None) -> BaseStrategy:
    strategies = {
        "sma": SMACrossover,
        "rsi": RSIStrategy,
        "macd": MACDStrategy,
        "bollinger": BollingerBandsStrategy,
    }
    try:
        strategy_class = strategies[name.lower()]
    except KeyError as exc:
        raise ValueError(f"Unknown strategy '{name}'. Choose from: sma, rsi, macd, bollinger") from exc
    return strategy_class(params or {})


__all__ = [
    "BaseStrategy",
    "BollingerBandsStrategy",
    "MACDStrategy",
    "RSIStrategy",
    "SMACrossover",
    "get_strategy",
]
