"""RSI(2) pullback, stricter version.
Same as the classic RSI(2) method, but buys only when the 2-day RSI drops below 5,
which ChartSchool's testing found worked better than 10. Price must be above its
200-day average. Sell when the price closes above its 5-day average. No stop
(Connors found stops hurt this method)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _indicators import rsi, sma  # noqa: E402

NAME = "RSI(2) pullback, below 5"
SOURCE = "StockCharts ChartSchool: RSI(2) (Larry Connors)"
STYLE = "rsi"
TIMEFRAME = "1Day"


def signal(bars, position):
    c = bars["c"]
    if len(c) < 201:
        return None
    if position is None:
        r = rsi(c, 2)
        return "buy" if c[-1] > sma(c, 200) and r is not None and r < 5 else None
    return "sell" if c[-1] > sma(c, 5) else None
