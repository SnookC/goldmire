"""MACD zero-line cross with swing points.
Buy when the MACD line (12/26/9) crosses above zero while price is making higher lows
(the lowest low of the last 20 days is above the lowest low of the 20 days before).
Exit with a stop trailed under the latest swing low: a close below the lowest low of the last 10 days."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _indicators import macd, lowest  # noqa: E402

NAME = "MACD zero-line cross + swing lows"
SOURCE = "StockCharts ChartSchool: MACD Zero-Line Crosses With Swing Points"
STYLE = "ma_cross"
TIMEFRAME = "1Day"


def signal(bars, position):
    c, l = bars["c"], bars["l"]
    if len(c) < 60:
        return None
    line, _, _ = macd(c)
    if len(line) < 2:
        return None
    if position is None:
        higher_lows = min(l[-20:]) > min(l[-40:-20])
        return "buy" if line[-2] <= 0 < line[-1] and higher_lows else None
    trail = lowest(l, 10)
    return "sell" if trail and c[-1] < trail else None
