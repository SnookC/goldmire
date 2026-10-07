"""Turtle-style breakout (the classic 1980s trend system, long side only).
Buy when the close breaks above the highest high of the last 20 days.
Sell when it breaks below the lowest low of the last 10 days,
or if price falls 2 x ATR(20) below the entry price."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _indicators import atr, highest, lowest  # noqa: E402

NAME = "Turtle breakout 20/10"
SOURCE = "Classic Turtle Trading rules (System 1)"
STYLE = "breakout"
TIMEFRAME = "1Day"
MARKETS = ("stock", "crypto")


def signal(bars, position):
    c = bars["c"]
    if len(c) < 25:
        return None
    if position is None:
        hi = highest(bars["h"], 20)
        return "buy" if hi and c[-1] > hi else None
    lo = lowest(bars["l"], 10)
    n = atr(bars, 20)
    if (lo and c[-1] < lo) or (n and c[-1] < position["entry"] - 2 * n):
        return "sell"
    return None
