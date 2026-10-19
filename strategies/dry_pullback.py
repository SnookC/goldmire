"""Dry pullback (Gareth's quant hypothesis #6, Oct 19 2026).
HYPOTHESIS: in an uptrend, a short pullback on SHRINKING volume is just a pause (few
sellers), and the first day it closes above the day before's high is the trend restarting.
Different from Wren's Bollinger bounce: it needs the trend intact and quiet selling,
not a deep oversold drop.
BUY when the 50-day average is above the 200-day, the stock is above its 200-day average,
it had 2 lower closes in a row on falling volume (the last one below its 20-day average
volume), and today it closes above yesterday's high.
SELL when the close falls below the lowest low of the last 10 days, or after 20 days.
WOULD BE FALSIFIED BY: losing money after costs in the exam, or doing no better than
random entries held as long."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _indicators import lowest, sma  # noqa: E402

NAME = "Dry pullback"
SOURCE = "Volume-confirmed pullbacks in an uptrend (classic tape reading; Granville's volume principles)"
STYLE = "ma_cross"
TIMEFRAME = "1Day"
MARKETS = ("stock",)


def signal(bars, position):
    c, h, v = bars["c"], bars["h"], bars["v"]
    if len(c) < 205:
        return None
    if position is None:
        if not (sma(c, 50) > sma(c, 200) and c[-1] > sma(c, 200)):
            return None
        down = c[-3] < c[-4] and c[-2] < c[-3]
        drying = v[-4] > v[-3] > v[-2] and v[-2] < sum(v[-22:-2]) / 20
        return "buy" if down and drying and c[-1] > h[-2] else None
    lo = lowest(bars["l"], 10)
    return "sell" if (lo and c[-1] < lo) or position["bars_held"] >= 20 else None
