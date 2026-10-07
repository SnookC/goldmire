"""
How heroes get out of a trade: stop-losses, "let it build" trailing exits, and cool-downs.
Shared by the heroes (bot.py) and the Proving Grounds (backtest.py), so a test means
exactly what the heroes will do.

Settings per hero in bots.json:
  "stop_loss": "smart"    a stop sized to how jumpy the symbol is (the default):
                          2.5 x its typical daily move, never tighter than 2% or wider than 15%.
                          Calm stocks get a tight stop, wild coins a wide one.
               0.05       a fixed stop: sell if down 5%
               null       no stop at all
  "exit": "signal"        sell when the hero's style says sell (the default)
          "build"         let winners build: once a trade is up by its stop distance,
                          ignore the style's sell signal and trail a stop behind the best
                          price instead (sell if it falls back by the stop distance)
After a stop-loss (or a bad-news exit) the hero won't buy that symbol again for 24 hours.
"""

import math

SMART_MULTIPLE = 2.5
SMART_MIN, SMART_MAX = 0.02, 0.15
VOL_WINDOW = 120                     # bars used to measure how jumpy a symbol is
COOLDOWN_HOURS = 24
BARS_PER_DAY = {"stock": {"15Min": 26, "1Hour": 7, "1Day": 1}, "crypto": {"15Min": 96, "1Hour": 24, "1Day": 1}}
DEFAULT_STOP = "smart"
DEFAULT_EXIT = "signal"


def daily_move(closes, market="stock", timeframe="15Min"):
    """Typical size of one day's move, as a fraction (0.02 = 2%), from recent closes."""
    c = [x for x in closes[-VOL_WINDOW - 1:] if x and x > 0]
    if len(c) < 20:
        return None
    rets = [math.log(b / a) for a, b in zip(c[:-1], c[1:])]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    per_day = BARS_PER_DAY["crypto" if market == "crypto" else "stock"].get(timeframe, 26)
    return math.sqrt(var * per_day)


def stop_fraction(setting, closes, market="stock", timeframe="15Min"):
    """The stop distance for a new trade (fraction of the entry price), or None for no stop."""
    if setting in (None, "", "none", False):
        return None
    if setting == "smart":
        move = daily_move(closes, market, timeframe)
        if move is None:
            return 0.08                       # not enough history to measure: a middle-of-the-road stop
        return round(min(SMART_MAX, max(SMART_MIN, SMART_MULTIPLE * move)), 4)
    return float(setting)


def trailing_active(exit_mode, stop, entry, peak):
    """'Let it build' mode kicks in once the best price since buying is up by one stop distance."""
    return exit_mode == "build" and bool(stop) and bool(entry) and peak >= entry * (1 + stop)


def describe(setting, exit_mode):
    s = ("a smart stop (sized to how jumpy each symbol is)" if setting == "smart" else
         "no stop" if setting in (None, "", "none") else f"a {float(setting):.0%} stop")
    return s + (", letting winners build" if exit_mode == "build" else "")
