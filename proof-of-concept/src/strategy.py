# strategy.py

prices = []

def simple_sma_strategy(row, short_window=3, long_window=5):
    """
    Simple SMA crossover strategy
    Buy when short SMA > long SMA
    Sell when short SMA < long SMA
    """
    global prices
    prices.append(row['Close'])
    
    if len(prices) < long_window:
        return 'hold'
    
    short_sma = sum(prices[-short_window:]) / short_window
    long_sma = sum(prices[-long_window:]) / long_window
    
    if short_sma > long_sma:
        return 'buy'
    elif short_sma < long_sma:
        return 'sell'
    else:
        return 'hold'