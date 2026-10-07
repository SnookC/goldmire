"""Short-term pullback in an uptrend (the well-known 2-period RSI method).
Buy when the close is above its 200-day average and the 2-day RSI is below 10.
Sell when the close rises above its 5-day average."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _indicators import rsi, sma  # noqa: E402

NAME = "RSI(2) pullback"
SOURCE = "StockCharts ChartSchool: RSI(2) (Larry Connors)"
STYLE = "rsi"
TIMEFRAME = "1Day"
MARKETS = ("stock", "crypto")


def signal(bars, position):
    c = bars["c"]
    if len(c) < 201:
        return None
    if position is None:
        r = rsi(c, 2)
        return "buy" if c[-1] > sma(c, 200) and r is not None and r < 10 else None
    return "sell" if c[-1] > sma(c, 5) else None
