"""12-1 momentum in fair weather (round 4, idea #9 for Gareth, Oct 20 2026).
HYPOTHESIS: plain 12-1 momentum only rode the market (idea #1). Momentum is known to crash
when the market turns, so a version that buys only in FAIR market weather and gets out when
the market turns STORMY should keep the trend-riding and avoid the crashes.
RULES: 12-1 momentum's buy rule (12-month return skipping the last month above +10%, above the
50- and 200-day averages) only while the market weather is FAIR; sell on its usual rules
(below the 100-day average, or 6-month return negative) OR when the weather turns STORMY.
WOULD BE FALSIFIED BY: doing no better than random entries held as long, or losing money in the exam."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _indicators import sma  # noqa: E402
from _weather import fair, weather  # noqa: E402

NAME = "12-1 momentum (fair weather)"
SOURCE = "Time-series momentum + market-regime filter (Daniel & Moskowitz 2016, 'Momentum crashes')"
STYLE = "ma_cross"
TIMEFRAME = "1Day"
MARKETS = ("stock",)
NEEDS_MARKET = True


def signal(bars, position):
    c = bars["c"]
    if len(c) < 253:
        return None
    if position is None:
        mom = c[-22] / c[-253] - 1
        return "buy" if mom > 0.10 and c[-1] > sma(c, 50) and c[-1] > sma(c, 200) and fair(bars.get("m")) else None
    w = weather(bars.get("m"))
    if w and w["state"] == "STORMY":
        return "sell"
    return "sell" if c[-1] < sma(c, 100) or c[-1] < c[-127] else None
