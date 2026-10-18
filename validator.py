"""
Old Bram the Validator: no hero opens new trades with a strategy the tests have failed.

Bram reads the two test reports Goldmire already makes:
  * the Proving Grounds  (backtest.py  -> proving_grounds/results.json):  is the STRATEGY any good?
  * the Hero Trials      (hero_test.py -> proving_grounds/heroes.json):   is the HERO, as set up today, earning its keep?

and gives each working hero one of four verdicts:

  PASS                   Proving Grounds PASSES and the Hero Trials say EARNING
  CONDITIONAL            some evidence for it, not yet enough (e.g. PASSES but the trial is only SO-SO):
                         allowed while trading on PAPER, because paper trading is the next test
  FAIL                   the Proving Grounds FAILS it in this market, or the Hero Trials say LOSING
  INSUFFICIENT EVIDENCE  no test result for this strategy in this market

FAIL and INSUFFICIENT EVIDENCE block NEW buys (what the hero holds is still managed and
sold by its rules). You can overrule Bram for one hero with "owner_approved": true in
bots.json; that exception is written in the log every time Goldmire starts.

A Hero Trials result only counts if it tested the hero's CURRENT strategy and market.
Bram reads the reports; he never edits them, and he never changes a hero's strategy.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "proving_grounds", "results.json")
TRIALS = os.path.join(HERE, "proving_grounds", "heroes.json")
BLOCKING = {"FAIL", "INSUFFICIENT EVIDENCE"}


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def market_of(bot):
    return {"crypto": "crypto", "penny": "penny"}.get(bot.get("kind"), "stock")


def judge(bot, results=None, trials=None):
    """(verdict, reasons list, evidence dict) for one hero."""
    results = _read(RESULTS) if results is None else results
    trials = _read(TRIALS) if trials is None else trials
    strat, market = bot.get("strategy"), market_of(bot)
    pg = next((r for r in results.get("results", []) if r.get("key") == strat and r.get("market") == market
               and not r.get("builtin")), None)
    trial = next((t for t in trials.get("results", []) if t.get("name") == bot.get("name")
                  and t.get("strategy") == strat and t.get("market") == market), None)
    pg_v = pg.get("verdict") if pg else None
    tr_v = trial.get("verdict") if trial else None
    ev = {"proving_grounds": pg_v, "proving_grounds_run": results.get("run"), "hero_trials": tr_v,
          "hero_trials_run": trials.get("run") if trial else None}
    why = []
    if pg_v:
        why.append(f"Proving Grounds: {pg_v} ({pg.get('why', '')})")
    else:
        why.append(f"Proving Grounds: no pass/fail result for {strat} on {market}"
                   + (" (it's a built-in style, tested only against other settings)" if strat in ("ma_cross", "rsi", "breakout") else ""))
    if tr_v:
        why.append(f"Hero Trials: {tr_v} ({trial.get('why', '')})")
    else:
        why.append("Hero Trials: no trial of this hero's current strategy")
    if pg_v == "FAILS" or tr_v == "LOSING":
        verdict = "FAIL"
    elif pg_v == "PASSES" and tr_v == "EARNING":
        verdict = "PASS"
    elif pg_v in ("PASSES", "PROMISING") or tr_v in ("EARNING", "SO-SO"):
        verdict = "CONDITIONAL"
    else:
        verdict = "INSUFFICIENT EVIDENCE"
    return verdict, why, ev


def review(bots, memory, log=print):
    """Judge every working hero at start-up; keep the verdicts in memory['validation']."""
    results, trials = _read(RESULTS), _read(TRIALS)
    out = {}
    for b in bots:
        if b.get("benched"):
            continue
        verdict, why, ev = judge(b, results, trials)
        approved = bool(b.get("owner_approved"))
        out[b["name"]] = {"verdict": verdict, "why": why, "evidence": ev, "owner_approved": approved,
                          "blocks_buys": verdict in BLOCKING and not approved}
        hero = b.get("hero", b["name"])
        if verdict in BLOCKING and approved:
            log(f"Bram: {hero} is {verdict}, but you approved this hero anyway (owner_approved): buys allowed")
        elif verdict in BLOCKING:
            log(f"Bram: {hero} is {verdict}: no new buys until a test passes (or you set \"owner_approved\": true)")
        else:
            log(f"Bram: {hero} is {verdict}")
        for w in why:
            log(f"    {w}")
    memory["validation"] = out
    return out


def blocks(memory, bot):
    """(blocked?, verdict) for one working hero. A hero sent back to work since start-up is judged now."""
    v = memory.setdefault("validation", {}).get(bot["name"])
    if v is None:
        verdict, why, ev = judge(bot)
        approved = bool(bot.get("owner_approved"))
        v = memory["validation"][bot["name"]] = {"verdict": verdict, "why": why, "evidence": ev, "owner_approved": approved,
                                                 "blocks_buys": verdict in BLOCKING and not approved}
    return bool(v.get("blocks_buys")), v.get("verdict")
