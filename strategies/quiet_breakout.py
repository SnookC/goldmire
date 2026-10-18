"""Quiet breakout (Gareth's quant hypothesis #3, Oct 2026).
HYPOTHESIS: a breakout to a 3-month high that comes after an unusually CALM stretch is
more likely to keep going than a breakout from a wild one, because calm stretches mean
sellers have dried up (volatility contraction).
BUY when the close beats the highest high of the last 63 days, on volume at least 1.3 x
its 20-day average, while the stock's typical daily move (ATR(14) / price) is in the
calmest third of its last year.
SELL when the close falls below the lowest low of the last 20 days, or 2 x ATR(14) below
the entry.
WOULD BE FALSIFIED BY: losing money after costs in the exam, or doing no better than
random entries held as long."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _indicators import atr, highest, lowest  # noqa: E402

NAME = "Quiet breakout"
SOURCE = "Volatility contraction before breakouts (Crabel, 'Day Trading with Short Term Price Patterns'; Minervini VCP)"
STYLE = "breakout"
TIMEFRAME = "1Day"
MARKETS = ("stock",)


def _calm_rank(bars, n=14, look=252, step=5):
    """Where today's ATR/price sits among the last year's (0 = calmest, 1 = wildest)."""
    c = bars["c"]
    now = atr(bars, n)
    if not now or len(c) < look + n + 1:
        return None
    now /= c[-1]
    past = []
    for back in range(step, look, step):
        sub = {k: bars[k][:-back] for k in ("h", "l", "c")}
        a = atr(sub, n)
        if a:
            past.append(a / sub["c"][-1])
    return sum(1 for x in past if x < now) / len(past) if past else None


def signal(bars, position):
    c, v = bars["c"], bars["v"]
    if len(c) < 270:
        return None
    if position is None:
        hi = highest(bars["h"], 63)
        avg_v = sum(v[-21:-1]) / 20
        if not hi or c[-1] <= hi or avg_v <= 0 or v[-1] < 1.3 * avg_v:
            return None
        rank = _calm_rank(bars)
        return "buy" if rank is not None and rank <= 1 / 3 else None
    lo, a = lowest(bars["l"], 20), atr(bars, 14)
    if (lo and c[-1] < lo) or (a and c[-1] < position["entry"] - 2 * a):
        return "sell"
    return None
