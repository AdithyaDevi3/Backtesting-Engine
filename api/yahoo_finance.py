import yfinance as yf

class YahooFinanceClient:
    def get_daily(self, symbol="AAPL"):
        df = yf.download(symbol, period="max", interval="1d")
        return df