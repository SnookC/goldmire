"""Gap-and-hold drift (Gareth's quant hypothesis #2, Oct 2026).
HYPOTHESIS: when a stock gaps up on news with heavy volume AND holds the gain all day,
the price keeps drifting the same way for days to weeks (like post-earnings drift),
because the market takes time to fully price surprising news.
BUY at the close of a day that opened at least 3% above the day before, traded at least
twice its usual (20-day) volume, closed above its open and in the top 30% of the day's
range, while above its 50-day average.
SELL after 15 days, or if it closes 1.5 x ATR(14) below the entry, or (after 5 days)
below its 20-day average.
WOULD BE FALSIFIED BY: losing money after costs in the exam, or doing no better than
random entries held as long."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _indicators import atr, sma  # noqa: E402

NAME = "Gap-and-hold drift"
SOURCE = "Post-earnings-announcement drift (Ball & Brown 1968; Bernard & Thomas 1989), gap version"
STYLE = "breakout"
TIMEFRAME = "1Day"
MARKETS = ("stock",)


def signal(bars, position):
    o, h, l, c, v = bars["o"], bars["h"], bars["l"], bars["c"], bars["v"]
    if len(c) < 60:
        return None
    if position is None:
        avg_v = sum(v[-21:-1]) / 20
        rng = h[-1] - l[-1]
        gap = o[-1] / c[-2] - 1
        strong = rng > 0 and (c[-1] - l[-1]) / rng >= 0.70
        return "buy" if gap >= 0.03 and avg_v > 0 and v[-1] >= 2 * avg_v and c[-1] > o[-1] and strong and c[-1] > sma(c, 50) else None
    a = atr(bars, 14)
    if position["bars_held"] >= 15 or (a and c[-1] < position["entry"] - 1.5 * a):
        return "sell"
    if position["bars_held"] >= 5 and c[-1] < sma(c, 20):
        return "sell"
    return None
