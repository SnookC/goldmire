"""Turtle breakout, slow version (System 2).
Buy when the close breaks above the highest high of the last 55 days.
Sell when it breaks below the lowest low of the last 20 days, or 2 x ATR(20)
below the entry price."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _indicators import atr, highest, lowest  # noqa: E402

NAME = "Turtle breakout 55/20"
SOURCE = "Classic Turtle Trading rules (System 2)"
STYLE = "breakout"
TIMEFRAME = "1Day"


def signal(bars, position):
    c = bars["c"]
    if len(c) < 60:
        return None
    if position is None:
        hi = highest(bars["h"], 55)
        return "buy" if hi and c[-1] > hi else None
    lo, n = lowest(bars["l"], 20), atr(bars, 20)
    if (lo and c[-1] < lo) or (n and c[-1] < position["entry"] - 2 * n):
        return "sell"
    return None
