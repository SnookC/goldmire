"""MACD signal-line crossover with a trend filter.
MACD 12/26/9. Buy when the MACD line crosses above its signal line while the price is
above the 200-day average. Sell when the MACD line crosses back below the signal line."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _indicators import macd, sma, crossed_above, crossed_below  # noqa: E402

NAME = "MACD crossover + 200-day filter"
SOURCE = "Classic MACD (Gerald Appel) 12/26/9; StockCharts ChartSchool: MACD"
STYLE = "ma_cross"
TIMEFRAME = "1Day"


def signal(bars, position):
    c = bars["c"]
    if len(c) < 201:
        return None
    line, sig, _ = macd(c)
    if len(sig) < 2:
        return None
    if position is None:
        return "buy" if c[-1] > sma(c, 200) and crossed_above(line[-2], line[-1], sig[-2], sig[-1]) else None
    return "sell" if crossed_below(line[-2], line[-1], sig[-2], sig[-1]) else None
