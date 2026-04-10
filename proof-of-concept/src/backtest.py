# backtest.py
import pandas as pd
from strategy import simple_sma_strategy

class BacktestEngine:
    def __init__(self, data, initial_cash=10000):
        self.data = data
        self.cash = initial_cash
        self.position = 0
        self.history = []

    def run(self, strategy):
        for idx, row in self.data.iterrows():
            signal = strategy(row)

            if signal == 'buy' and self.cash >= row['Close']:
                self.position += 1
                self.cash -= row['Close']
                self.history.append((row['Date'], 'buy', row['Close'], self.position, self.cash))
            elif signal == 'sell' and self.position > 0:
                self.position -= 1
                self.cash += row['Close']
                self.history.append((row['Date'], 'sell', row['Close'], self.position, self.cash))
            else:
                self.history.append((row['Date'], 'hold', row['Close'], self.position, self.cash))

        final_value = self.cash + self.position * self.data.iloc[-1]['Close']
        return final_value, pd.DataFrame(self.history, columns=['Date', 'Action', 'Price', 'Position', 'Cash'])


if __name__ == "__main__":
    data = pd.read_csv('data/data.csv', parse_dates=['Date'])
    engine = BacktestEngine(data)
    final_value, history = engine.run(simple_sma_strategy)

    print("Final Portfolio Value:", final_value)
    print(history)