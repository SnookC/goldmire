"""Percent B + Money Flow (strength confirmed by buying pressure).
Buy when %B (20-day Bollinger, 2 deviations) is above 0.80 and the 14-day Money Flow
Index is above 80, and they weren't both there the day before.
Exit when the Parabolic SAR (0.02/0.2) flips above the price, as Bollinger suggests."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _indicators import bollinger, mfi, psar  # noqa: E402

NAME = "Percent B + Money Flow"
SOURCE = "StockCharts ChartSchool: Percent B Money Flow (John Bollinger)"
STYLE = "breakout"
TIMEFRAME = "1Day"
STOP_LOSS = 0.08


def _pb(c):
    mid, up, low = bollinger(c, 20, 2)
    return (c[-1] - low) / (up - low) if up != low else 0.5


def signal(bars, position):
    c = bars["c"]
    if len(c) < 40:
        return None
    if position is None:
        now = _pb(c) > 0.8 and (mfi(bars, 14) or 0) > 80
        prev_bars = {k: v[:-1] for k, v in bars.items()}
        before = _pb(c[:-1]) > 0.8 and (mfi(prev_bars, 14) or 0) > 80
        return "buy" if now and not before else None
    s = psar(bars)
    return "sell" if s and not s[-1][1] else None
