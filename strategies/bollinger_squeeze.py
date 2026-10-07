"""Bollinger Band squeeze breakout.
Bands: 20 days, 2 standard deviations. A squeeze is when BandWidth (upper minus lower,
as a share of the middle) is near its 6-month low: within 10% of the lowest of the last
125 days, at some point in the last 5 days. Buy when the price closes above the upper
band during a squeeze, with the price above its 50-day average (direction clue).
Exit on a close back below the middle band."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _indicators import bollinger, bandwidth_series, sma  # noqa: E402

NAME = "Bollinger squeeze breakout"
SOURCE = "StockCharts ChartSchool: Bollinger Band Squeeze"
STYLE = "breakout"
TIMEFRAME = "1Day"
STOP_LOSS = 0.08


def signal(bars, position):
    c = bars["c"]
    if len(c) < 150:
        return None
    mid, up, _ = bollinger(c, 20, 2)
    if position is None:
        bw = bandwidth_series(c, 20, 2, 130)
        squeezed = min(bw[-5:]) <= min(bw[-125:]) * 1.10
        return "buy" if squeezed and c[-1] > up and c[-1] > sma(c, 50) else None
    return "sell" if c[-1] < mid else None
