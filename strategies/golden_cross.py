"""Golden cross trend (50/200-day averages).
Buy while the 50-day average is above the 200-day average (the "golden cross" state)
and the price is above the 50-day. Sell on the death cross: 50-day back below the 200-day."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _indicators import sma  # noqa: E402

NAME = "Golden cross 50/200"
SOURCE = "Classic golden/death cross; StockCharts ChartSchool: Moving Average Trading Strategies"
STYLE = "ma_cross"
TIMEFRAME = "1Day"


def signal(bars, position):
    c = bars["c"]
    if len(c) < 201:
        return None
    fast, slow = sma(c, 50), sma(c, 200)
    if position is None:
        return "buy" if fast > slow and c[-1] > fast else None
    return "sell" if fast < slow else None
