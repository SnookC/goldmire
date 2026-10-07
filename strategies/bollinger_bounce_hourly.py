"""Bollinger Band bounce on hourly bars (same rules, faster).
Buy when the price closes below the lower band (20 bars, 2 standard deviations) while
above its 200-bar average. Sell when it closes back above the middle band."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _indicators import bollinger, sma  # noqa: E402

NAME = "Bollinger bounce (hourly)"
SOURCE = "Classic Bollinger Band mean reversion, hourly version"
STYLE = "rsi"
TIMEFRAME = "1Hour"
STOP_LOSS = 0.06


def signal(bars, position):
    c = bars["c"]
    if len(c) < 201:
        return None
    mid, _, low = bollinger(c, 20, 2)
    if position is None:
        return "buy" if c[-1] < low and c[-1] > sma(c, 200) else None
    return "sell" if c[-1] > mid else None
