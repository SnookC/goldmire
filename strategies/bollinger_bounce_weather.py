"""Bollinger bounce in fair weather (round 4, idea #8, Oct 20 2026).
HYPOTHESIS: Wren's dip-buying works when the whole market is calm and rising and gets hurt
when the market is falling or very jumpy (dips keep dipping). So only buying in FAIR market
weather should keep most of her gains and cut her worst trades.
RULES: exactly Wren's Bollinger bounce (buy a close below the lower band while above the
200-day average, sell back at the middle band), but NEW buys only while the market weather
(see _weather.py: S&P 500 above its 200-day average and not unusually jumpy) is FAIR.
WOULD BE FALSIFIED BY: doing no better than random entries held as long, or losing money in the
exam. It must also beat plain Bollinger bounce to be worth using."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _indicators import bollinger, sma  # noqa: E402
from _weather import fair  # noqa: E402

NAME = "Bollinger bounce (fair weather)"
SOURCE = "Wren's Bollinger bounce + a market-regime filter (Faber 2007, 'A Quantitative Approach to Tactical Asset Allocation')"
STYLE = "rsi"
TIMEFRAME = "1Day"
MARKETS = ("stock",)
NEEDS_MARKET = True


def signal(bars, position):
    c = bars["c"]
    if len(c) < 201:
        return None
    mid, _, low = bollinger(c, 20, 2)
    if position is None:
        return "buy" if c[-1] < low and c[-1] > sma(c, 200) and fair(bars.get("m")) else None
    return "sell" if c[-1] > mid else None
