"""Shared helpers for strategy files.
Every function takes plain lists (oldest first) and returns None when there isn't enough data."""
import math


def sma(values, n):
    return sum(values[-n:]) / n if len(values) >= n else None


def sma_series(values, n):
    if len(values) < n:
        return []
    out, s = [], sum(values[:n])
    out.append(s / n)
    for i in range(n, len(values)):
        s += values[i] - values[i - n]
        out.append(s / n)
    return out


def ema_series(values, n):
    """Exponential moving average for every bar from the n-th on."""
    if len(values) < n:
        return []
    k, e = 2 / (n + 1), sum(values[:n]) / n
    out = [e]
    for v in values[n:]:
        e = v * k + e * (1 - k)
        out.append(e)
    return out


def ema(values, n):
    s = ema_series(values, n)
    return s[-1] if s else None


def rsi(closes, n=14):
    """RSI over the last n changes (simple average, like the classic short-period RSI tests)."""
    if len(closes) < n + 1:
        return None
    gains = losses = 0.0
    for a, b in zip(closes[-n - 1:-1], closes[-n:]):
        d = b - a
        gains += max(d, 0)
        losses += max(-d, 0)
    if losses == 0:
        return 100.0
    return 100 - 100 / (1 + gains / losses)


def macd(closes, fast=12, slow=26, signal=9):
    """(macd line, signal line, histogram) as lists aligned to the most recent bars."""
    ef, es = ema_series(closes, fast), ema_series(closes, slow)
    if not es:
        return [], [], []
    ef = ef[len(ef) - len(es):]
    line = [a - b for a, b in zip(ef, es)]
    sig = ema_series(line, signal)
    if not sig:
        return line, [], []
    line = line[len(line) - len(sig):]
    return line, sig, [a - b for a, b in zip(line, sig)]


def stochastic(bars, n=14, smooth=3):
    """Slow %K (the %K line most charts show): list for the most recent bars."""
    h, l, c = bars["h"], bars["l"], bars["c"]
    if len(c) < n + smooth:
        return []
    fast = []
    for i in range(n - 1, len(c)):
        hi, lo = max(h[i - n + 1:i + 1]), min(l[i - n + 1:i + 1])
        fast.append(50.0 if hi == lo else (c[i] - lo) / (hi - lo) * 100)
    return sma_series(fast, smooth) if smooth > 1 else fast


def atr(bars, n=14):
    """Average true range: the typical size of one bar's move."""
    h, l, c = bars["h"], bars["l"], bars["c"]
    if len(c) < n + 1:
        return None
    trs = [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(len(c) - n, len(c))]
    return sum(trs) / n


def bollinger(closes, n=20, k=2.0):
    """(middle, upper, lower) for the latest bar."""
    if len(closes) < n:
        return None
    w = closes[-n:]
    m = sum(w) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in w) / n)
    return m, m + k * sd, m - k * sd


def bandwidth_series(closes, n=20, k=2.0, count=130):
    """(upper - lower) / middle for the last `count` bars."""
    out = []
    for end in range(max(n, len(closes) - count + 1), len(closes) + 1):
        b = bollinger(closes[:end], n, k)
        out.append((b[1] - b[2]) / b[0] if b and b[0] else 0.0)
    return out


def cci(bars, n=20):
    """Commodity Channel Index for the latest bar."""
    h, l, c = bars["h"], bars["l"], bars["c"]
    if len(c) < n:
        return None
    tp = [(h[i] + l[i] + c[i]) / 3 for i in range(len(c) - n, len(c))]
    m = sum(tp) / n
    md = sum(abs(x - m) for x in tp) / n
    return 0.0 if md == 0 else (tp[-1] - m) / (0.015 * md)


def cci_series(bars, n=20, count=30):
    out = []
    for end in range(max(n, len(bars["c"]) - count + 1), len(bars["c"]) + 1):
        out.append(cci({k: v[:end] for k, v in bars.items()}, n))
    return out


def adx(bars, n=14):
    """(ADX, +DI, -DI) for the latest bar, Wilder's smoothing."""
    h, l, c = bars["h"], bars["l"], bars["c"]
    if len(c) < 2 * n + 2:
        return None
    tr_s = pdm_s = mdm_s = 0.0
    dxs = []
    for i in range(1, len(c)):
        up, down = h[i] - h[i - 1], l[i - 1] - l[i]
        pdm = up if up > down and up > 0 else 0.0
        mdm = down if down > up and down > 0 else 0.0
        tr = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        if i <= n:
            tr_s, pdm_s, mdm_s = tr_s + tr, pdm_s + pdm, mdm_s + mdm
            if i < n:
                continue
        else:
            tr_s, pdm_s, mdm_s = tr_s - tr_s / n + tr, pdm_s - pdm_s / n + pdm, mdm_s - mdm_s / n + mdm
        pdi = 100 * pdm_s / tr_s if tr_s else 0.0
        mdi = 100 * mdm_s / tr_s if tr_s else 0.0
        dxs.append((100 * abs(pdi - mdi) / (pdi + mdi) if pdi + mdi else 0.0, pdi, mdi))
    if len(dxs) < n:
        return None
    a = sum(d[0] for d in dxs[:n]) / n
    for d in dxs[n:]:
        a = (a * (n - 1) + d[0]) / n
    return a, dxs[-1][1], dxs[-1][2]


def psar(bars, step=0.02, max_step=0.2):
    """Parabolic SAR: list of (sar, rising) for every bar from the second on."""
    h, l = bars["h"], bars["l"]
    if len(h) < 3:
        return []
    rising, af = h[1] >= h[0], step
    sar, ep = (l[0], h[1]) if rising else (h[0], l[1])
    out = []
    for i in range(1, len(h)):
        sar = sar + af * (ep - sar)
        if rising:
            sar = min(sar, l[i - 1], l[i - 2] if i >= 2 else l[i - 1])
            if l[i] < sar:
                rising, sar, ep, af = False, ep, l[i], step
            elif h[i] > ep:
                ep, af = h[i], min(af + step, max_step)
        else:
            sar = max(sar, h[i - 1], h[i - 2] if i >= 2 else h[i - 1])
            if h[i] > sar:
                rising, sar, ep, af = True, ep, h[i], step
            elif l[i] < ep:
                ep, af = l[i], min(af + step, max_step)
        out.append((sar, rising))
    return out


def mfi(bars, n=14):
    """Money Flow Index for the latest bar."""
    h, l, c, v = bars["h"], bars["l"], bars["c"], bars["v"]
    if len(c) < n + 1:
        return None
    pos = neg = 0.0
    for i in range(len(c) - n, len(c)):
        tp, tp0 = (h[i] + l[i] + c[i]) / 3, (h[i - 1] + l[i - 1] + c[i - 1]) / 3
        if tp > tp0:
            pos += tp * v[i]
        elif tp < tp0:
            neg += tp * v[i]
    if neg == 0:
        return 100.0
    return 100 - 100 / (1 + pos / neg)


def highest(values, n, skip_last=True):
    """Highest of the n values before the current one (skip_last) or including it."""
    w = values[-n - 1:-1] if skip_last else values[-n:]
    return max(w) if len(w) == n else None


def lowest(values, n, skip_last=True):
    w = values[-n - 1:-1] if skip_last else values[-n:]
    return min(w) if len(w) == n else None


def crossed_above(a_prev, a_now, b_prev, b_now):
    return None not in (a_prev, a_now, b_prev, b_now) and a_prev <= b_prev and a_now > b_now


def crossed_below(a_prev, a_now, b_prev, b_now):
    return None not in (a_prev, a_now, b_prev, b_now) and a_prev >= b_prev and a_now < b_now
