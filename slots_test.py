"""
What should Wren do when all her slots are full? (written Nov 18 2026, before testing)

Wren holds up to 12 stocks. When all 12 are taken she can't act on a new buy signal, and if they're
all waiting for a bounce that hasn't come, she can sit full for weeks. The usual Proving Grounds test
can't show this: it scores every stock on its own, as if there were always room. This one replays
her 12 slots for real: one $1,000 pot, $83.33 a slot, the 300 largest US companies, 5 years of daily
prices, her own rule (buy a close below the lower Bollinger band while above the 200-day average; sell
a close above the 20-day average), decisions at the close, orders filled at the next open, the usual
0.05% cost each way.

  * now                       what she does today: when full, new signals are skipped
  * your swap                 the owner's idea: when full and a stock gives a buy signal, sell the
                              holding with the SMALLEST GAIN among those in the green and buy the new
                              one (never one at a loss), at most 2 switches a day
  * time limit (20 days)      sell any holding that hasn't bounced back within 20 trading days
                              (about 4 weeks), win or lose, so stuck stocks free their slot
  * swap the nearly-done one  like your swap, but sell the green holding that's CLOSEST to Wren's own
                              sell point (the one with the least bounce left), at most 2 a day

When several stocks signal on the same day, which one gets a free slot depends on the order they
are looked at, so every version is run 30 times with 30 different random orders (the same 30 for
each version) and the results are averaged.

THE RULE: a version replaces "now" only if, averaged over the 30 orders, it
  1. makes at least 5% more money than "now" over the 5 years (and more in dollars), AND
  2. makes more in the exam (the most recent 30% of the time), AND
  3. beats "now" in at least 60% of the 30 orders.
If more than one qualifies, the one that makes the most wins. Otherwise Wren keeps doing what she does.

FOLLOW-UP (Nov 18 2026, after "your swap" won, before testing): the owner asked about 3 or 4 swaps a day
instead of 2. run_limits() replays "your swap" with 2 (the winner), 3 and 4 a day, the same 30 orders.
A higher limit replaces 2 only if it makes at least 5% more money than 2 a day, makes more in the exam,
and beats 2 a day in at least 60% of the orders; if both qualify, the one that makes the most wins.
6 a day and no limit are shown for information only.
The 10- and 40-day time limits are also shown, for information only (they can't win).
Not modelled (the same for every version): news exits, Pip's limits, the crypto-fund block.
"""
import json
import os
import random
from datetime import datetime

import backtest
import lab

OUT_JSON = os.path.join(backtest.OUT_DIR, "slots_test.json")
OUT_LIMITS = os.path.join(backtest.OUT_DIR, "slots_test_limits.json")
LIMITS = [(2, True), (3, True), (4, True), (6, False), (99, False)]    # (swaps a day, counts for the decision?)
SLOTS = 12
POT = 1000.0
SEEDS = 30
MARGIN = 0.05
WIN_SHARE = 0.60
SWAPS_PER_DAY = 2
VARIANTS = [  # (name, swap kind, time limit in trading days, counts for the decision?)
    ("now", None, None, True),
    ("your swap (smallest green gain)", "smallest", None, True),
    ("time limit (20 days)", None, 20, True),
    ("swap the nearly-done one", "nearly_done", None, True),
    ("time limit (10 days)", None, 10, False),
    ("time limit (40 days)", None, 40, False),
]


def due():
    return not os.path.exists(OUT_JSON) or not os.path.exists(OUT_LIMITS)


def prepare(data):
    """Wren's buy/sell signals for every stock and day, worked out once (same maths as bollinger_bounce.py)."""
    import math
    prep, buys_on = {}, {}
    for sym, s in data.items():
        c, o, t = s.get("c") or [], s.get("o") or [], s.get("t") or []
        n = len(c)
        if n < 230:
            continue
        mid, buy, sell = [None] * n, [False] * n, [False] * n
        s20 = sum(c[:20])
        q20 = sum(x * x for x in c[:20])
        s200 = sum(c[:200])
        for i in range(19, n):
            if i >= 20:
                s20 += c[i] - c[i - 20]
                q20 += c[i] * c[i] - c[i - 20] * c[i - 20]
            m = s20 / 20
            mid[i] = m
            if i >= 200:
                s200 += c[i] - c[i - 200]
                sd = math.sqrt(max(q20 / 20 - m * m, 0.0))
                low = m - 2 * sd
                buy[i] = c[i] < low and c[i] > s200 / 200
                sell[i] = c[i] > m
        days = [x[:10] for x in t]
        prep[sym] = {"c": c, "o": o, "mid": mid, "buy": buy, "sell": sell, "idx": {d: i for i, d in enumerate(days)}}
        for i in range(200, n - 1):
            if buy[i]:
                buys_on.setdefault(days[i], []).append(sym)
    dates = sorted({d for p in prep.values() for d in p["idx"]})
    for d in buys_on:
        buys_on[d].sort()
    return prep, buys_on, dates


def simulate(prep, buys_on, dates, swap=None, limit=None, seed=0, cost=None, per_day=SWAPS_PER_DAY):
    """One run of the 12 slots. Returns money made, the exam part, worst drop, trades and how often she missed out."""
    cost = backtest.COST["stock"] if cost is None else cost
    rng = random.Random(seed)
    stake = POT / SLOTS
    held, trades = {}, []
    realized, missed, swaps, full_days = 0.0, 0, 0, 0
    curve = []
    for k, d in enumerate(dates):
        # value at today's close
        open_pl = 0.0
        for sym, pos in held.items():
            i = prep[sym]["idx"].get(d)
            if i is not None:
                pos["last"] = prep[sym]["c"][i]
            open_pl += (pos["last"] * (1 - cost) / pos["px"] - 1) * stake
        curve.append(realized + open_pl)
        if k == len(dates) - 1:
            break
        # decisions at the close, filled at each stock's next open
        sells = {}
        for sym, pos in held.items():
            i = prep[sym]["idx"].get(d)
            if i is None or i + 1 >= len(prep[sym]["o"]):
                continue
            if prep[sym]["sell"][i]:
                sells[sym] = "signal"
            elif limit and i - pos["i"] >= limit:
                sells[sym] = "time limit"
        cands = [s for s in buys_on.get(d, []) if s not in held]
        rng.shuffle(cands)
        free = SLOTS - (len(held) - len(sells))
        take, rest = cands[:max(free, 0)], cands[max(free, 0):]
        if rest:
            full_days += 1
            if swap:
                green = []
                for sym, pos in held.items():
                    i = prep[sym]["idx"].get(d)
                    if sym in sells or i is None or i + 1 >= len(prep[sym]["o"]):
                        continue
                    price = prep[sym]["c"][i]
                    if price <= pos["raw"]:
                        continue                                    # never at a loss
                    if swap == "smallest":
                        key = price / pos["raw"] - 1                # smallest gain first (same stake, so % = $)
                    else:
                        m = prep[sym]["mid"][i]
                        key = -((price - pos["raw"]) / (m - pos["raw"])) if m and m > pos["raw"] else -9.0   # least bounce left first
                    green.append((key, sym))
                green.sort()
                n_sw = min(len(green), per_day, len(rest))
                for (_, out), new in zip(green[:n_sw], rest[:n_sw]):
                    sells[out] = "swap"
                    take.append(new)
                    swaps += 1
                rest = rest[n_sw:]
            missed += len(rest)
        for sym, why in sells.items():
            pos = held.pop(sym)
            i = prep[sym]["idx"][d]
            fill = prep[sym]["o"][i + 1] * (1 - cost)
            pl = (fill / pos["px"] - 1) * stake
            realized += pl
            trades.append({"pl": pl, "days": i + 1 - pos["i"], "why": why})
        for sym in take:
            i = prep[sym]["idx"][d]
            if i + 1 >= len(prep[sym]["o"]):
                continue
            raw = prep[sym]["o"][i + 1]
            held[sym] = {"i": i + 1, "raw": raw, "px": raw * (1 + cost), "last": raw}
    cut = int(len(curve) * (1 - backtest.EXAM_SHARE))
    peak, worst = 0.0, 0.0
    for v in curve:
        peak = max(peak, v)
        worst = max(worst, peak - v)
    wins = [t for t in trades if t["pl"] > 0]
    return {"pl": curve[-1], "exam_pl": curve[-1] - curve[cut], "max_drawdown": worst, "trades": len(trades),
            "win_rate": len(wins) / len(trades) if trades else 0.0, "avg_days": sum(t["days"] for t in trades) / len(trades) if trades else 0.0,
            "missed": missed, "swaps": swaps, "full_days": full_days,
            "time_limit_sales": sum(1 for t in trades if t["why"] == "time limit"),
            "time_limit_pl": sum(t["pl"] for t in trades if t["why"] == "time limit")}


def _data(log):
    return backtest.fetch_history("stock", "1Day", log, symbols=lab.universe(), tag="300", days=lab.BIG_YEARS * 365 + 350)


def run_all(log=print):
    """Whatever is still due: the main test, then the swaps-a-day follow-up."""
    data = None
    if not os.path.exists(OUT_JSON):
        data = _data(log)
        run(log, data)
    if not os.path.exists(OUT_LIMITS):
        run_limits(log, data or _data(log))


def run_limits(log=print, data=None, seeds=SEEDS):
    data = data if data is not None else _data(log)
    prep, buys_on, dates = prepare(data)
    log(f"Slots test (follow-up): your swap with {', '.join(str(n) if n < 99 else 'no limit' for n, _ in LIMITS)} switches a day")
    res = {}
    for n, _ in LIMITS:
        runs = [simulate(prep, buys_on, dates, "smallest", None, seed, per_day=n) for seed in range(seeds)]
        avg = {k: round(sum(r[k] for r in runs) / len(runs), 2) for k in runs[0]}
        avg["runs_pl"] = [round(r["pl"], 2) for r in runs]
        name = f"{n} a day" if n < 99 else "no limit"
        res[name] = avg
        log(f"    {name}: ${avg['pl']:+,.2f} (exam ${avg['exam_pl']:+,.2f}), {avg['trades']:.0f} trades, {avg['win_rate']:.0%} won, "
            f"worst drop ${avg['max_drawdown']:,.2f}, {avg['swaps']:.0f} swaps")
    base = res["2 a day"]
    ok = []
    for n, counts in LIMITS[1:]:
        name = f"{n} a day" if n < 99 else "no limit"
        r = res[name]
        r["beats_2_share"] = round(sum(1 for a, b in zip(r["runs_pl"], base["runs_pl"]) if a > b) / len(base["runs_pl"]), 2)
        if counts and (r["pl"] > base["pl"] and r["pl"] >= base["pl"] + abs(base["pl"]) * MARGIN
                       and r["exam_pl"] > base["exam_pl"] and r["beats_2_share"] >= WIN_SHARE):
            ok.append(name)
    best = max(ok, key=lambda k: res[k]["pl"]) if ok else "2 a day"
    verdict = f"USE {best.upper()}" if ok else "KEEP 2 A DAY"
    why = (f"{best} made ${res[best]['pl']:+,.2f} vs ${base['pl']:+,.2f} with 2 a day (exam ${res[best]['exam_pl']:+,.2f} vs "
           f"${base['exam_pl']:+,.2f}), better in {res[best]['beats_2_share']:.0%} of the orders" if ok else
           f"neither 3 nor 4 a day beat 2 a day (${base['pl']:+,.2f}, exam ${base['exam_pl']:+,.2f}) by the rule's margins")
    out = {"run": datetime.now().isoformat(timespec="seconds"), "seeds": seeds, "results": res, "verdict": verdict, "why": why,
           "best_per_day": int(best.split()[0]) if best[0].isdigit() else None}
    os.makedirs(backtest.OUT_DIR, exist_ok=True)
    with open(OUT_LIMITS, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    log(f"Slots test (follow-up): {verdict}. {why}")
    return out


def run(log=print, data=None, seeds=SEEDS):
    if data is None:
        log(f"Slots test: what Wren should do when her {SLOTS} slots are full; downloading 300 stocks x {lab.BIG_YEARS} years")
        data = backtest.fetch_history("stock", "1Day", log, symbols=lab.universe(), tag="300", days=lab.BIG_YEARS * 365 + 350)
    prep, buys_on, dates = prepare(data)
    log(f"Slots test: {len(prep)} stocks, {len(dates)} days, {sum(len(v) for v in buys_on.values())} buy signals; "
        f"{len(VARIANTS)} versions x {seeds} random orders")
    res = {}
    for name, swap, limit, _ in VARIANTS:
        runs = [simulate(prep, buys_on, dates, swap, limit, seed) for seed in range(seeds)]
        avg = {k: round(sum(r[k] for r in runs) / len(runs), 2) for k in runs[0]}
        avg["runs_pl"] = [round(r["pl"], 2) for r in runs]
        res[name] = avg
        log(f"    {name}: ${avg['pl']:+,.2f} over {lab.BIG_YEARS} years (exam ${avg['exam_pl']:+,.2f}), {avg['trades']:.0f} trades, "
            f"{avg['win_rate']:.0%} won, worst drop ${avg['max_drawdown']:,.2f}, missed {avg['missed']:.0f} signals"
            + (f", {avg['swaps']:.0f} swaps" if swap else "") + (f", {avg['time_limit_sales']:.0f} time-limit sales" if limit else ""))
    base = res["now"]
    ok = []
    for name, _, _, counts in VARIANTS[1:]:
        if not counts:
            continue
        r = res[name]
        beat = sum(1 for a, b in zip(r["runs_pl"], base["runs_pl"]) if a > b) / len(base["runs_pl"])
        r["beats_now_share"] = round(beat, 2)
        if (r["pl"] > base["pl"] and r["pl"] >= base["pl"] + abs(base["pl"]) * MARGIN and r["exam_pl"] > base["exam_pl"]
                and beat >= WIN_SHARE):
            ok.append(name)
    best = max(ok, key=lambda n: res[n]["pl"]) if ok else None
    verdict = f"SWITCH TO: {best.upper()}" if best else "KEEP WHAT WREN DOES NOW"
    why = (f"{best} made ${res[best]['pl']:+,.2f} vs ${base['pl']:+,.2f} now (exam ${res[best]['exam_pl']:+,.2f} vs "
           f"${base['exam_pl']:+,.2f}), better in {res[best]['beats_now_share']:.0%} of the random orders" if best else
           f"nothing beat 'now' (${base['pl']:+,.2f}, exam ${base['exam_pl']:+,.2f}) by the rule's margins")
    out = {"run": datetime.now().isoformat(timespec="seconds"), "slots": SLOTS, "pot": POT, "years": lab.BIG_YEARS, "seeds": seeds,
           "stocks": len(prep), "days": len(dates), "results": res, "verdict": verdict, "why": why, "qualified": ok}
    os.makedirs(backtest.OUT_DIR, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    log(f"Slots test: {verdict}. {why}")
    return out


if __name__ == "__main__":
    run()
