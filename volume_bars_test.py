"""
Volume candles vs time candles (round 7, written Oct 27 2026 before testing).

A normal (time) candle closes every day at 4:00 pm. A VOLUME candle closes once a set number
of shares has traded, however long that takes: busy days make several candles, quiet days get
folded together. Idea from Marcos Lopez de Prado, "Advances in Financial Machine Learning".

Both kinds are built from the SAME minute-by-minute prices (Alpaca's free data, regular hours
only), for the 60-stock list over the last YEARS years, so the only difference is the clock:
  * time candles:   one candle per trading day
  * volume candles: one candle each time the shares traded reach the stock's average daily
                    volume over the 20 days before (so about one a day on average, more when
                    it's busy). Only past days set the size: no peeking ahead.
Note: Alpaca's free minute data only counts trades on the IEX exchange (a few % of all trading).
Busy days are busy there too, so it's a fair stand-in, not the full count.

Tested on both: Wren's Bollinger bounce, Bollinger + candle, and the three candle patterns.
THE RULES:
  * Wren moves to volume candles only if Bollinger bounce PASSES on them AND makes more than on
    the time candles from the same minutes, in the exam too.
  * A candle pattern (or MACD, added the same day) earns Gareth a strategy only if it PASSES
    on volume candles.
"""
import json
import os
import time
from datetime import datetime, timedelta, timezone

import backtest

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(backtest.OUT_DIR, "volume_bars.json")
CACHE = os.path.join(backtest.OUT_DIR, "data", "volume_bars_cache.json")
YEARS = 3
AVG_DAYS = 20
STRATEGIES = ["bollinger_bounce", "bollinger_bounce_candle", "hammer_reversal", "engulfing_reversal", "morning_star_reversal",
              "macd_signal_cross", "macd_zero_cross"]


def due():
    return not os.path.exists(OUT_JSON)


_OFFSETS = {}


def _ny_offset_minutes(day):
    """Minutes New York is behind UTC on that date (240 in summer, 300 in winter)."""
    if day not in _OFFSETS:
        from zoneinfo import ZoneInfo
        d = datetime.fromisoformat(day + "T17:00:00+00:00")
        _OFFSETS[day] = int(-d.astimezone(ZoneInfo("America/New_York")).utcoffset().total_seconds() // 60)
    return _OFFSETS[day]


def build(minutes):
    """minutes: list of (iso utc time, o, h, l, c, v), oldest first.
    Returns (time candles, volume candles) as backtest series dicts."""
    days = {"t": [], "o": [], "h": [], "l": [], "c": [], "v": []}
    vols = {"t": [], "o": [], "h": [], "l": [], "c": [], "v": []}
    cur_day, d = None, None
    vb, done_vols = None, []
    for t, o, h, l, c, v in minutes:
        day = t[:10]
        m = int(t[11:13]) * 60 + int(t[14:16]) - _ny_offset_minutes(day)
        if not 570 <= m < 960:                       # regular hours only, 9:30 to 4:00 New York
            continue
        if day != cur_day:
            if d:
                for k in days:
                    days[k].append(d[k])
                done_vols.append(d["v"])
            cur_day = day
            d = {"t": day + "T20:00:00+00:00", "o": o, "h": h, "l": l, "c": c, "v": 0.0}
        d["h"], d["l"], d["c"], d["v"] = max(d["h"], h), min(d["l"], l), c, d["v"] + v
        if len(done_vols) < 5:
            continue                                 # need a few days to know what "a day's volume" is
        size = sum(done_vols[-AVG_DAYS:]) / len(done_vols[-AVG_DAYS:])
        if vb is None:
            vb = {"o": o, "h": h, "l": l, "c": c, "v": 0.0}
        vb["h"], vb["l"], vb["c"], vb["v"] = max(vb["h"], h), min(vb["l"], l), c, vb["v"] + v
        if vb["v"] >= size:
            vb["t"] = t.replace("Z", "+00:00")
            for k in vols:
                vols[k].append(vb[k])
            vb = None
    if d:
        for k in days:
            days[k].append(d[k])
    return days, vols


def fetch_minutes(raw_client, symbol, start, end, log):
    """All regular minute bars for one symbol, a quarter at a time (keeps memory small)."""
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.data.enums import DataFeed
    out, t = [], start
    while t < end:
        t2 = min(end, t + timedelta(days=92))
        got = raw_client.get_stock_bars(StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Minute,
                                                         start=t, end=t2, feed=DataFeed.IEX))
        rows = got.get(symbol, []) if isinstance(got, dict) else got.data.get(symbol, [])
        for r in rows:
            if isinstance(r, dict):
                out.append((str(r["t"]), float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"]), float(r["v"] or 0)))
            else:
                out.append((r.timestamp.isoformat().replace("+00:00", "Z"), float(r.open), float(r.high), float(r.low),
                            float(r.close), float(r.volume or 0)))
        t = t2
    out.sort(key=lambda x: x[0])
    return out


def run(raw_client, log=print, years=YEARS, symbols=None):
    symbols = symbols or backtest.WIDE_BASKET
    end = datetime.now(timezone.utc) - timedelta(minutes=20)
    start = end - timedelta(days=int(years * 365.25))
    cache = {}
    try:
        with open(CACHE, encoding="utf-8") as f:
            cache = json.load(f)
        if cache.get("years") != years:
            cache = {}
    except (OSError, ValueError):
        cache = {}
    cache.setdefault("years", years)
    cache.setdefault("time", {})
    cache.setdefault("volume", {})
    todo = [s for s in symbols if s not in cache["time"]]
    log(f"Volume candles: building candles from minute prices for {len(todo)} stocks, {years} years (about 15-30 min)")
    t0 = time.time()
    for i, sym in enumerate(todo, 1):
        try:
            mins = fetch_minutes(raw_client, sym, start, end, log)
        except Exception as e:  # noqa: BLE001
            log(f"    {sym}: couldn't download minute prices ({e}); skipped")
            continue
        days, vols = build(mins)
        del mins
        if len(days["c"]) >= 250 and len(vols["c"]) >= 250:
            cache["time"][sym], cache["volume"][sym] = days, vols
        if i % 10 == 0 or i == len(todo):
            log(f"    ...{i} of {len(todo)} stocks done ({time.time() - t0:.0f}s)")
            os.makedirs(os.path.dirname(CACHE), exist_ok=True)
            with open(CACHE, "w", encoding="utf-8") as f:
                json.dump(cache, f)
    res = {}
    for key in STRATEGIES:
        st = backtest.load_strategy_file(os.path.join(HERE, "strategies", key + ".py"))
        row = {}
        for kind in ("time", "volume"):
            s = backtest.test(st, "stock", cache[kind])
            s["verdict"], s["why"] = backtest.verdict(s, None)
            row[kind] = {k: s.get(k) for k in ("verdict", "why", "trades", "pl", "exam_pl", "win_rate", "profit_factor",
                                                "beats_random", "breadth", "buy_and_hold")}
            log(f"Volume candles: {st.name} on {kind} candles: {s['verdict']}, {s['trades']} trades, ${s['pl']:+,.2f}, "
                f"exam ${s['exam_pl']:+,.2f}, beats {s.get('beats_random', 0):.0%} of random")
        res[key] = {"name": st.name, **row}
    b = res["bollinger_bounce"]
    wren = (b["volume"]["verdict"] == "PASSES" and b["volume"]["pl"] > b["time"]["pl"]
            and b["volume"]["exam_pl"] > b["time"]["exam_pl"])
    gareth = [res[k]["name"] for k in ("hammer_reversal", "engulfing_reversal", "morning_star_reversal",
                                       "macd_signal_cross", "macd_zero_cross")
              if res[k]["volume"]["verdict"] == "PASSES"]
    verdict = ("SWITCH WREN TO VOLUME CANDLES" if wren else "KEEP TIME CANDLES FOR WREN") + \
              (f"; for Gareth: {', '.join(gareth)} passes on volume candles" if gareth else "; nothing for Gareth")
    out = {"run": datetime.now(timezone.utc).isoformat(timespec="seconds"), "years": years, "stocks": len(cache["time"]),
           "candles": {k: sum(len(v["c"]) for v in cache[k].values()) for k in ("time", "volume")},
           "results": res, "verdict": verdict}
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    log(f"Volume candles: {verdict} ({out['candles']['time']} time candles vs {out['candles']['volume']} volume candles)")
    return out
