"""CCI Correction: buy the dip inside an uptrend (single-chart version).
Bias: bullish after the 100-day CCI surges above +100 (until it drops below -100).
Trigger: the 20-day CCI plunges below -100, then surges back above zero.
Exit: after the 20-day CCI gets above +100, sell when it moves back below +100;
or when the bias turns bearish."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _indicators import cci_series  # noqa: E402

NAME = "CCI correction"
SOURCE = "StockCharts ChartSchool: CCI Correction (single-timeframe version: 100-day bias, 20-day signals)"
STYLE = "rsi"
TIMEFRAME = "1Day"
STOP_LOSS = 0.08


def _bias(long_cci):
    for v in reversed(long_cci):
        if v > 100:
            return "bull"
        if v < -100:
            return "bear"
    return None


def signal(bars, position):
    c = bars["c"]
    if len(c) < 160:
        return None
    long_cci = cci_series(bars, 100, 60)
    short = cci_series(bars, 20, 25)
    bull = _bias(long_cci) == "bull"
    if position is None:
        dipped = min(short[-15:-1]) < -100
        return "buy" if bull and dipped and short[-2] <= 0 < short[-1] else None
    if not bull:
        return "sell"
    was_hot = max(short[-10:-1]) > 100
    return "sell" if was_hot and short[-1] < 100 <= short[-2] else None
