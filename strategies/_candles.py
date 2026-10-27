"""Candlestick patterns on daily bars (o, h, l, c lists; the last item is today).
Classic textbook definitions (Steve Nison, "Japanese Candlestick Charting Techniques"), made exact
so a computer can test them. All of them only call the pattern after a short decline."""
from _indicators import sma


def _parts(o, h, l, c, i=-1):
    body = abs(c[i] - o[i])
    rng = h[i] - l[i]
    return body, rng, min(o[i], c[i]) - l[i], h[i] - max(o[i], c[i])


def after_decline(c, i=-1):
    """The close before the pattern sits below its own 10-day average."""
    k = len(c) + i if i < 0 else i
    prev = c[:k]
    return len(prev) >= 10 and prev[-1] < sma(prev, 10)


def hammer(o, h, l, c):
    """Long lower tail (at least twice the body), little or no upper tail, at a 10-day low."""
    body, rng, lower, upper = _parts(o, h, l, c)
    return rng > 0 and lower >= 2 * max(body, rng * 0.05) and upper <= 0.25 * rng and l[-1] <= min(l[-10:]) and after_decline(c)


def bullish_engulfing(o, h, l, c):
    """A down day, then an up day whose body swallows it whole."""
    return (c[-2] < o[-2] and c[-1] > o[-1] and o[-1] <= c[-2] and c[-1] >= o[-2]
            and (c[-1] - o[-1]) > (o[-2] - c[-2]) and after_decline(c, -2))


def morning_star(o, h, l, c):
    """A long down day, a small-bodied day below it, then an up day closing above the middle of the first."""
    b3 = o[-3] - c[-3]
    if b3 <= 0:
        return False
    avg_body = sum(abs(c[k] - o[k]) for k in range(-13, -3)) / 10
    small = abs(c[-2] - o[-2]) <= 0.3 * b3 and max(o[-2], c[-2]) < c[-3]
    return b3 > avg_body and small and c[-1] > o[-1] and c[-1] > (o[-3] + c[-3]) / 2 and after_decline(c, -3)
