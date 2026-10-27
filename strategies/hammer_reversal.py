"""Hammer candle after a decline, in an uptrend (above the 200-day average).
Buy the next open. Sell when the close gets back above the 20-day average, or after 10 days.
Round 5 (Oct 27 2026): a candlestick idea for Gareth. See EXPERIMENTS.txt."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _indicators import sma  # noqa: E402
from _candles import hammer  # noqa: E402

NAME = "Hammer reversal"
SOURCE = "Steve Nison, Japanese Candlestick Charting Techniques (classic reversal pattern)"
STYLE = "rsi"
TIMEFRAME = "1Day"
MARKETS = ("stock",)


def signal(bars, position):
    o, h, l, c = bars["o"], bars["h"], bars["l"], bars["c"]
    if len(c) < 201:
        return None
    if position is None:
        return "buy" if c[-1] > sma(c, 200) and hammer(o, h, l, c) else None
    return "sell" if c[-1] > sma(c, 20) or position["bars_held"] >= 10 else None
