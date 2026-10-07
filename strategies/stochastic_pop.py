"""Stochastic Pop: buy the breakout from a quiet, sideways stretch.
Bias: 70-day Stochastic above 50. Quiet market: 14-day ADX below 20.
Trigger: the 14-day Stochastic surges above 80 on above-average volume (above the
250-day average). Exit when the 14-day Stochastic falls back below 50."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _indicators import stochastic, adx, sma  # noqa: E402

NAME = "Stochastic pop"
SOURCE = "StockCharts ChartSchool: Stochastic Pop and Drop (Jake Bernstein, modified by Steve Primo)"
STYLE = "breakout"
TIMEFRAME = "1Day"
STOP_LOSS = 0.08


def signal(bars, position):
    c, v = bars["c"], bars["v"]
    if len(c) < 260:
        return None
    k14 = stochastic(bars, 14, 3)
    if len(k14) < 2:
        return None
    if position is None:
        k70 = stochastic(bars, 70, 3)
        a = adx(bars, 14)
        if not k70 or not a:
            return None
        loud = v[-1] > sma(v[:-1], 250)
        return "buy" if k70[-1] > 50 and a[0] < 20 and k14[-2] <= 80 < k14[-1] and loud else None
    return "sell" if k14[-1] < 50 else None
