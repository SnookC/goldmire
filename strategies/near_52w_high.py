"""Near the 52-week high (Gareth's quant hypothesis #5, Oct 19 2026).
HYPOTHESIS: investors use the 52-week high as an anchor and are slow to push a stock
through it, so stocks trading right at their 52-week high keep drifting higher as good
news gets priced in late (George & Hwang's anchoring explanation, which is different
from plain momentum).
BUY when the close is within 2% of the highest high of the last 252 days and above its
50-day average.
SELL when the close falls more than 10% below that 52-week high, or after 120 days.
WOULD BE FALSIFIED BY: losing money after costs in the exam, or doing no better than
random entries held as long."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _indicators import sma  # noqa: E402

NAME = "Near the 52-week high"
SOURCE = "George & Hwang (2004) 'The 52-Week High and Momentum Investing', Journal of Finance"
STYLE = "ma_cross"
TIMEFRAME = "1Day"
MARKETS = ("stock",)


def signal(bars, position):
    c, h = bars["c"], bars["h"]
    if len(c) < 253:
        return None
    hi = max(h[-252:])
    if position is None:
        return "buy" if c[-1] >= 0.98 * hi and c[-1] > sma(c, 50) else None
    return "sell" if c[-1] < 0.90 * hi or position["bars_held"] >= 120 else None
