"""12-1 momentum with a trend filter (Gareth's quant hypothesis #1, Oct 2026).
HYPOTHESIS: stocks that rose over the past year (leaving out the most recent month) keep
drifting up for a few months ("time-series momentum"), because investors under-react.
BUY when the 12-month return, skipping the last month, is above +10% and the price is
above both its 50-day and 200-day averages.
SELL when the price closes below its 100-day average, or the 6-month return turns negative.
WOULD BE FALSIFIED BY: losing money after costs in the exam (last 30%), or doing no better
than random entries held as long."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _indicators import sma  # noqa: E402

NAME = "12-1 momentum"
SOURCE = "Time-series momentum (Moskowitz, Ooi & Pedersen 2012); Jegadeesh & Titman 12-1 lookback"
STYLE = "ma_cross"
TIMEFRAME = "1Day"
MARKETS = ("stock",)


def signal(bars, position):
    c = bars["c"]
    if len(c) < 253:
        return None
    if position is None:
        mom = c[-22] / c[-253] - 1
        return "buy" if mom > 0.10 and c[-1] > sma(c, 50) and c[-1] > sma(c, 200) else None
    return "sell" if c[-1] < sma(c, 100) or c[-1] < c[-127] else None
