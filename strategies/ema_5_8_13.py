"""5-8-13 EMA ribbon (short-term).
Buy when the 5, 8 and 13-bar exponential averages line up upward (5 > 8 > 13) after
not being lined up on the previous bar. Sell when the 5 drops below the 13. Hourly bars."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _indicators import ema_series  # noqa: E402

NAME = "5-8-13 EMA ribbon (hourly)"
SOURCE = "StockCharts ChartSchool: Moving Average Trading Strategies (5-8-13 EMA crossover)"
STYLE = "ma_cross"
TIMEFRAME = "1Hour"


def _lined_up(e5, e8, e13, i):
    return e5[i] > e8[i] > e13[i]


def signal(bars, position):
    c = bars["c"]
    if len(c) < 30:
        return None
    e5, e8, e13 = ema_series(c, 5)[-2:], ema_series(c, 8)[-2:], ema_series(c, 13)[-2:]
    if position is None:
        return "buy" if _lined_up(e5, e8, e13, -1) and not _lined_up(e5, e8, e13, -2) else None
    return "sell" if e5[-1] < e13[-1] else None
