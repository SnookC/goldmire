"""NR7 breakout: a quiet day often comes before a big move.
NR7 = the day with the narrowest high-low range of the last 7 days.
Buy when the day after an NR7 day closes above the NR7 day's high, in an uptrend
(price above its 50-day average) and with a 10-day CCI that was oversold (below -100)
within the last 5 days. Take profits fast: sell on the first profitable close, or after
5 days, or if the price closes 2 ATRs below the entry."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _indicators import sma, cci_series, atr  # noqa: E402

NAME = "NR7 breakout"
SOURCE = "StockCharts ChartSchool: Narrow Range Day (NR7), Toby Crabel"
STYLE = "breakout"
TIMEFRAME = "1Day"


def signal(bars, position):
    h, l, c = bars["h"], bars["l"], bars["c"]
    if len(c) < 60:
        return None
    if position is None:
        ranges = [h[i] - l[i] for i in range(len(c) - 8, len(c) - 1)]
        nr7 = ranges[-1] == min(ranges)
        oversold = min(cci_series(bars, 10, 6)[:-1]) < -100
        return "buy" if nr7 and c[-1] > h[-2] and c[-1] > sma(c, 50) and oversold else None
    a = atr(bars, 14) or 0
    if c[-1] > position["entry"] * 1.006 or position["bars_held"] >= 5 or c[-1] < position["entry"] - 2 * a:
        return "sell"
    return None
