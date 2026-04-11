from api.base_client import BaseClient
from utils.config import ALPHA_VANTAGE_API_KEY
import pandas as pd

class AlphaVantageClient(BaseClient):
    BASE_URL = "https://www.alphavantage.co/query"

    def get_daily(self, symbol="AAPL"):
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "apikey": ALPHA_VANTAGE_API_KEY
        }
        data = self.get(self.BASE_URL, params)
        if not data:
            return None

        ts = data.get("Time Series (Daily)", {})
        df = pd.DataFrame.from_dict(ts, orient="index")
        df = df.rename(columns={
            "1. open": "open",
            "2. high": "high",
            "3. low": "low",
            "4. close": "close",
            "5. volume": "volume"
        })
        df.index = pd.to_datetime(df.index)
        return df.sort_index()
