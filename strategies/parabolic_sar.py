"""Parabolic SAR trend rider.
Buy when the SAR (0.02 step, 0.2 max) flips below the price while the price is above its
50-day average. Sell when the SAR flips back above the price."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _indicators import psar, sma  # noqa: E402

NAME = "Parabolic SAR"
SOURCE = "Classic Parabolic SAR (J. Welles Wilder)"
STYLE = "ma_cross"
TIMEFRAME = "1Day"


def signal(bars, position):
    c = bars["c"]
    if len(c) < 60:
        return None
    s = psar(bars)
    if len(s) < 2:
        return None
    if position is None:
        return "buy" if s[-1][1] and not s[-2][1] and c[-1] > sma(c, 50) else None
    return "sell" if not s[-1][1] else None
