"""ADX trend strength with directional lines.
Buy when the +DI line crosses above the -DI line while the 14-day ADX is above 25
(a strong trend). Sell when -DI moves back above +DI."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _indicators import adx  # noqa: E402

NAME = "ADX + directional lines"
SOURCE = "Classic ADX/DMI (J. Welles Wilder); StockCharts ChartSchool: Average Directional Index"
STYLE = "ma_cross"
TIMEFRAME = "1Day"
STOP_LOSS = 0.08


def signal(bars, position):
    if len(bars["c"]) < 60:
        return None
    now = adx(bars, 14)
    before = adx({k: v[:-1] for k, v in bars.items()}, 14)
    if not now or not before:
        return None
    if position is None:
        return "buy" if now[0] > 25 and before[1] <= before[2] and now[1] > now[2] else None
    return "sell" if now[2] > now[1] else None
