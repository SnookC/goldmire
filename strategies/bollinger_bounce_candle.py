"""Bollinger bounce, confirmed by a candle (for Wren).
Wren's rule, but instead of buying the moment the price closes below the lower band, wait for
a reversal candle (hammer or bullish engulfing) at the band: today's low touched the lower band
(or yesterday closed below it), and today's candle says buyers stepped in. Still only above the
200-day average. Sell when it closes back above the middle band, like Wren.
Round 5 (Oct 27 2026). See EXPERIMENTS.txt."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _indicators import bollinger, sma  # noqa: E402
from _candles import hammer, bullish_engulfing  # noqa: E402

NAME = "Bollinger bounce + candle"
SOURCE = "Bollinger Bands (John Bollinger) + candlestick confirmation (Steve Nison)"
STYLE = "rsi"
TIMEFRAME = "1Day"
MARKETS = ("stock",)


def signal(bars, position):
    o, h, l, c = bars["o"], bars["h"], bars["l"], bars["c"]
    if len(c) < 201:
        return None
    mid, _, low = bollinger(c, 20, 2)
    if position is not None:
        return "sell" if c[-1] > mid else None
    _, _, low_prev = bollinger(c[:-1], 20, 2)
    at_band = l[-1] <= low or c[-2] < low_prev
    return "buy" if c[-1] > sma(c, 200) and at_band and (hammer(o, h, l, c) or bullish_engulfing(o, h, l, c)) else None
