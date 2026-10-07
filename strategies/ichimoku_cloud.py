"""Ichimoku cloud trend entry.
Conversion line (9), base line (26), cloud spans (26/52, shifted 26 ahead).
Buy when the price is above the cloud and the conversion line crosses above the base line.
Sell when the price closes below the base line."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _indicators import crossed_above  # noqa: E402

NAME = "Ichimoku cloud"
SOURCE = "Classic Ichimoku Kinko Hyo (Goichi Hosoda); StockCharts ChartSchool: Ichimoku Cloud"
STYLE = "ma_cross"
TIMEFRAME = "1Day"
STOP_LOSS = 0.08


def _mid(h, l, n, end):
    return (max(h[end - n:end]) + min(l[end - n:end])) / 2


def signal(bars, position):
    h, l, c = bars["h"], bars["l"], bars["c"]
    if len(c) < 90:
        return None
    n = len(c)
    conv, conv_prev = _mid(h, l, 9, n), _mid(h, l, 9, n - 1)
    base, base_prev = _mid(h, l, 26, n), _mid(h, l, 26, n - 1)
    span_a = (_mid(h, l, 9, n - 26) + _mid(h, l, 26, n - 26)) / 2     # today's cloud was drawn 26 days ago
    span_b = _mid(h, l, 52, n - 26)
    if position is None:
        above = c[-1] > max(span_a, span_b)
        return "buy" if above and crossed_above(conv_prev, conv, base_prev, base) else None
    return "sell" if c[-1] < base else None
