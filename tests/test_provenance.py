import pandas as pd
import pytest

from app.provenance import canonical_json, fingerprint_ohlcv, fingerprint_request


def market_data() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [10.0, 11.0],
            "high": [11.0, 12.0],
            "low": [9.0, 10.0],
            "close": [10.5, 11.5],
            "volume": [1000.0, 1100.0],
        },
        index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
    )


def test_canonical_request_fingerprint_ignores_mapping_order():
    first = {"ticker": "TEST", "params": {"short": 5, "long": 15}}
    second = {"params": {"long": 15, "short": 5}, "ticker": "TEST"}

    assert canonical_json(first) == canonical_json(second)
    assert fingerprint_request(first) == fingerprint_request(second)


def test_data_fingerprint_normalizes_row_order_and_detects_changes():
    frame = market_data()
    reversed_frame = frame.iloc[::-1]
    changed = frame.copy()
    changed.loc[pd.Timestamp("2024-01-02"), "close"] = 11.6

    assert fingerprint_ohlcv(frame) == fingerprint_ohlcv(reversed_frame)
    assert fingerprint_ohlcv(frame) != fingerprint_ohlcv(changed)


def test_data_fingerprint_rejects_duplicate_timestamps():
    frame = pd.concat([market_data(), market_data().iloc[[0]]])

    with pytest.raises(ValueError, match="duplicate"):
        fingerprint_ohlcv(frame)
