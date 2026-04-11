import os
from api.alpha_vantage import AlphaVantageClient
from api.yahoo_finance import YahooFinanceClient
from utils.config import DATA_DIR

os.makedirs(DATA_DIR, exist_ok=True)


def save_csv(df, filename):
    path = os.path.join(DATA_DIR, filename)
    df.to_csv(path)
    print(f"Saved: {path}")


def run():
    symbols = ["AAPL", "MSFT", "TSLA"]

    alpha_client = AlphaVantageClient()
    yahoo_client = YahooFinanceClient()

    for symbol in symbols:
        print(f"Fetching {symbol}...")

        # Alpha Vantage
        df_alpha = alpha_client.get_daily(symbol)
        if df_alpha is not None:
            save_csv(df_alpha, f"{symbol}_alpha.csv")

        # Yahoo Finance
        df_yahoo = yahoo_client.get_daily(symbol)
        if df_yahoo is not None:
            save_csv(df_yahoo, f"{symbol}_yahoo.csv")


if __name__ == "__main__":
    run()