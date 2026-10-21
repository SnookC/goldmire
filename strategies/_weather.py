"""Market weather: is the whole stock market calm and rising, or not? (shared helper, not a strategy)

Read from the S&P 500 fund (SPY), daily closes:
  * trend   : SPY above its 200-day average = the market's long trend is up
  * jumpiness: how much SPY has swung over the last 20 days (annualized), ranked against the
               last year: in the top 20% = unusually jumpy
Weather:
  FAIR    trend up and not unusually jumpy
  WINDY   trend up but unusually jumpy
  STORMY  trend down (below the 200-day average)
"""
import math

TREND_DAYS = 200
VOL_DAYS = 20
RANK_DAYS = 252
JUMPY_RANK = 0.80


def _vol(c, end):
    """Annualized swing of the 20 daily returns ending at index end (exclusive)."""
    rets = [math.log(c[i] / c[i - 1]) for i in range(end - VOL_DAYS, end) if c[i - 1] > 0 and c[i] > 0]
    if len(rets) < VOL_DAYS - 2:
        return None
    m = sum(rets) / len(rets)
    return math.sqrt(sum((r - m) ** 2 for r in rets) / len(rets)) * math.sqrt(252)


def weather(spy_closes):
    """{"state": FAIR/WINDY/STORMY, "trend_up", "vol", "vol_rank"} or None when there's too little history."""
    c = list(spy_closes or [])
    if len(c) < TREND_DAYS + 1:
        return None
    sma = sum(c[-TREND_DAYS:]) / TREND_DAYS
    trend_up = c[-1] > sma
    now = _vol(c, len(c))
    past = [v for v in (_vol(c, e) for e in range(max(VOL_DAYS + 1, len(c) - RANK_DAYS), len(c), 5)) if v is not None]
    rank = sum(1 for v in past if v < now) / len(past) if past and now is not None else 0.5
    state = "STORMY" if not trend_up else ("WINDY" if rank >= JUMPY_RANK else "FAIR")
    return {"state": state, "trend_up": trend_up, "vol": round(now or 0, 4), "vol_rank": round(rank, 2),
            "spy": round(c[-1], 2), "spy_200": round(sma, 2)}


def fair(spy_closes):
    w = weather(spy_closes)
    return bool(w and w["state"] == "FAIR")
