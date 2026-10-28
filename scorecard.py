"""
The Scorecard: are the traders doing as well live as their tests said, and better than
simply holding the S&P 500?

For each trader (not the guardians), counted from the day its current strategy started
(it starts over whenever its strategy changes):

  * RESULT      what its pot gained or lost since then, counting what it still holds
  * S&P 500     what the same money would have made sitting in the S&P 500 fund (SPY)
  * LIVE vs TEST  win rate and average result per finished trade, next to what the
                Proving Grounds measured for this strategy
  * VERDICT     TOO EARLY (fewer than MIN_TRADES finished trades), ON TRACK, or BEHIND:
                at least MIN_TRADES finished trades AND (win rate WIN_GAP points or more under
                the test's, or losing on average where the test made money). These rules were
                set before any live results came in (Oct 20 2026).

A BEHIND verdict is written to the log (and raises a Watchdog alert); it doesn't stop the
trader by itself: that's a decision for you, with Bram's help.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "proving_grounds", "results.json")
MIN_TRADES = 20
WIN_GAP = 0.15
TEST_TRADE_DOLLARS = 100.0


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _tested(strategy):
    try:
        with open(RESULTS, encoding="utf-8") as f:
            res = json.load(f)
    except (OSError, ValueError):
        return None
    r = next((x for x in res.get("results", []) if x.get("key") == strategy and x.get("market") == "stock"
              and not x.get("builtin")), None)
    if not r or not r.get("trades"):
        return None
    return {"win_rate": _f(r.get("win_rate")), "avg_return": _f(r.get("pl")) / r["trades"] / TEST_TRADE_DOLLARS,
            "trades": r["trades"], "verdict": r.get("verdict"), "run": res.get("run")}


def shift(memory, name, amount):
    """Money moved into (+) or out of (-) a trader's pot by you, not earned: move its starting
    point the same amount so the Scorecard's result doesn't count it."""
    st = memory.get("score_start", {}).get(name)
    if st:
        st["pot"] = round(st["pot"] + amount, 2)


# one-time corrections for money moved before shift() existed
FIXES = [("2026-10-28-gareth-spare", {"Stock-1": -219.41, "Stock-2": 219.41})]


def apply_fixes(memory):
    done = set(memory.setdefault("score_fixes", []))
    for uid, moves in FIXES:
        if uid in done:
            continue
        for name, amount in moves.items():
            shift(memory, name, amount)
        done.add(uid)
    memory["score_fixes"] = sorted(done)


def update(memory, bots, positions, spy_now, today, norm, pot_of, log=print):
    """Recompute every trader's scorecard. spy_now: the S&P 500 fund's latest close (or None)."""
    starts = memory.setdefault("score_start", {})
    out = []
    for b in bots:
        if b.get("role") or b.get("retired"):
            continue
        name = b["name"]
        held = {s: h for s, h in memory.get("held", {}).get(name, {}).items() if not h.get("hold")}   # your holds don't count
        unreal = sum(_f(getattr(positions.get(norm(s)), "unrealized_pl", 0)) for s in held if positions.get(norm(s)))
        pot = pot_of(b)
        st = starts.get(name)
        if not st or st.get("strategy") != b.get("strategy"):
            if not spy_now:
                continue                                   # start once the S&P 500 price is known
            st = starts[name] = {"day": today, "strategy": b.get("strategy"), "pot": round(pot, 2),
                                 "unreal": round(unreal, 2), "spy": spy_now}
        trades = [e for e in memory.get("journal", []) if e.get("side") == "sell" and e.get("bot") == name
                  and str(e.get("t", ""))[:10] >= st["day"] and "owner hold" not in str(e.get("reason", ""))]
        n = len(trades)
        wins = sum(1 for e in trades if _f(e.get("pl")) > 0)
        rets = [_f(e.get("pl")) / _f(e.get("cost")) for e in trades if _f(e.get("cost")) > 0]
        yours = sum(_f(e.get("pl")) for e in memory.get("journal", []) if e.get("side") == "sell" and e.get("bot") == name
                    and str(e.get("t", ""))[:10] >= st["day"] and "owner hold" in str(e.get("reason", "")))
        result = round((pot - st["pot"]) + (unreal - st["unreal"]) - yours, 2)      # your holds' sales aren't the trader's
        spy_ret = (spy_now / st["spy"] - 1) if spy_now and st.get("spy") else None
        tested = _tested(b.get("strategy"))
        live_win = wins / n if n else None
        live_avg = sum(rets) / len(rets) if rets else None
        if n < MIN_TRADES or not tested:
            verdict = "TOO EARLY" if n < MIN_TRADES else "NO TEST"
        elif live_win is not None and (live_win < tested["win_rate"] - WIN_GAP
                                       or (live_avg is not None and live_avg < 0 < tested["avg_return"])):
            verdict = "BEHIND"
        else:
            verdict = "ON TRACK"
        card = {"name": name, "hero": b.get("hero", name), "since": st["day"], "pot_start": st["pot"],
                "result": result, "result_pct": round(result / st["pot"], 4) if st["pot"] else None,
                "spy_pct": round(spy_ret, 4) if spy_ret is not None else None,
                "spy_result": round(st["pot"] * spy_ret, 2) if spy_ret is not None else None,
                "trades": n, "wins": wins, "live_win": round(live_win, 3) if live_win is not None else None,
                "live_avg": round(live_avg, 4) if live_avg is not None else None,
                "test_win": round(tested["win_rate"], 3) if tested else None,
                "test_avg": round(tested["avg_return"], 4) if tested else None,
                "verdict": verdict, "min_trades": MIN_TRADES}
        said = memory.setdefault("score_said", {})
        if verdict == "BEHIND" and said.get(name) != today:
            said[name] = today
            log(f"Scorecard: {card['hero']} is BEHIND its test: {n} trades, wins {live_win:.0%} vs {tested['win_rate']:.0%} "
                f"in the test, average {live_avg:+.1%} a trade vs {tested['avg_return']:+.1%}")
        out.append(card)
    return out
