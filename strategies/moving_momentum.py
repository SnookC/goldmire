"""Moving Momentum: buy pullbacks inside an uptrend.
Trend: 20-day average above the 150-day average.
Setup: the 14-day Stochastic dipped below 20 in the last 5 days (a pullback).
Trigger: the MACD histogram (12/26/9) turns positive.
Exit: after the Stochastic has been above 80, the MACD histogram turns negative;
or the trend breaks (20-day back below 150-day)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _indicators import sma, macd, stochastic  # noqa: E402

NAME = "Moving Momentum"
SOURCE = "StockCharts ChartSchool: Moving Momentum"
STYLE = "rsi"
TIMEFRAME = "1Day"
STOP_LOSS = 0.08


def signal(bars, position):
    c = bars["c"]
    if len(c) < 160:
        return None
    _, _, hist = macd(c)
    k = stochastic(bars, 14, 3)
    if len(hist) < 2 or len(k) < 5:
        return None
    uptrend = sma(c, 20) > sma(c, 150)
    turned_up, turned_down = hist[-2] <= 0 < hist[-1], hist[-2] >= 0 > hist[-1]
    if position is None:
        return "buy" if uptrend and min(k[-5:]) < 20 and turned_up else None
    if not uptrend or (max(k[-5:]) > 80 and turned_down):
        return "sell"
    return None
