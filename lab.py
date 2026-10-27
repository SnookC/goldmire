"""
The Lab: tests a batch of new strategy ideas in the Proving Grounds WITHOUT touching the main
results (results.json is what Bram and the Scorecard read, so it only changes when you run the
full test yourself).

Each idea is tested twice, with the standard Proving Grounds rules:
  * on the usual 12-stock list   -> proving_grounds/results_lab.json,      report_lab.html
  * on the 60-stock wide list    -> proving_grounds/results_lab_wide.json, report_lab_wide.html
Plain Bollinger bounce (Wren's strategy today) is re-run alongside, on the same prices, so the
ideas meant for Wren can be compared with it fairly.

What each idea needs to be adopted is written in strategies/EXPERIMENTS.txt BEFORE the run.
Goldmire runs this by itself in the background when the list of ideas changes.
"""
import json
import os
import time
from datetime import datetime

import backtest

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = backtest.OUT_DIR
IDEAS = ["bollinger_bounce_weather", "momentum_weather",                                  # round 4
         "hammer_reversal", "engulfing_reversal", "morning_star_reversal", "bollinger_bounce_candle"]   # round 5
FOR_WREN = {"bollinger_bounce_weather", "bollinger_bounce_candle"}
REFERENCE = "bollinger_bounce"
STATE = os.path.join(OUT_DIR, "lab_state.json")


def due():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f).get("ideas") != IDEAS
    except (OSError, ValueError):
        return True


def _best_builtin(suffix):
    """The heroes' best built-in result the Proving Grounds compared new ideas against last time."""
    try:
        with open(os.path.join(OUT_DIR, f"results{suffix}.json"), encoding="utf-8") as f:
            res = json.load(f)["results"]
        vals = [r.get("best_builtin_pl") for r in res if r.get("market") == "stock" and r.get("best_builtin_pl") is not None]
        return max(vals) if vals else None
    except (OSError, ValueError, KeyError):
        return None


def _run_one(label, data, strategies, best, suffix, log):
    results = []
    for st in strategies:
        t0 = time.time()
        s = backtest.test(st, "stock", data)
        r = {"key": st.key, "name": st.name, "market": "stock", "timeframe": st.timeframe, "builtin": False, "variant": None,
             "base": st.key, "exit_mode": st.exit_mode, "source": st.source, "rules": st.rules, "stop_loss": st.stop_loss,
             "take_profit": st.take_profit, "symbols": len(data), "bars": sum(len(v["c"]) for v in data.values()), **s}
        r["verdict"], r["why"] = backtest.verdict(r, best)
        r["best_builtin_pl"] = best
        results.append(r)
        log(f"Lab ({label}): {st.name}: {r['verdict']}, {s['trades']} trades, ${s['pl']:+,.2f}, exam ${s['exam_pl']:+,.2f}, "
            f"beats {s.get('beats_random', 0):.0%} of random  ({time.time() - t0:.0f}s)")
    report = {"run": datetime.now().isoformat(timespec="seconds"), "trade_dollars": backtest.TRADE_DOLLARS,
              "exam_share": backtest.EXAM_SHARE, "costs": backtest.COST, "results": results, "lab": True,
              "basket": "wide" if suffix else "standard"}
    with open(os.path.join(OUT_DIR, f"results_lab{suffix}.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    with open(os.path.join(OUT_DIR, f"report_lab{suffix}.html"), "w", encoding="utf-8") as f:
        f.write(backtest.render_html(report))
    return {r["key"]: r for r in results}


def run(log=print):
    os.makedirs(OUT_DIR, exist_ok=True)
    keys = IDEAS + [REFERENCE]
    strategies = [backtest.load_strategy_file(os.path.join(HERE, "strategies", k + ".py")) for k in keys]
    if any(st.needs_market for st in strategies):
        spy = backtest.fetch_history("stock", "1Day", log, symbols=["SPY"], tag="_mkt").get("SPY") or {}
        backtest.MARKET["d"], backtest.MARKET["c"] = [str(x)[:10] for x in spy.get("t", [])], list(spy.get("c", []))
    log(f"Lab: testing {len(IDEAS)} ideas (+ plain Bollinger bounce to compare) on 12 stocks, then on 60")
    std = _run_one("12 stocks", backtest.fetch_history("stock", "1Day", log), strategies, _best_builtin(""), "", log)
    wide = _run_one("60 stocks", backtest.fetch_history("stock", "1Day", log, symbols=backtest.WIDE_BASKET, tag="wide"),
                    strategies, _best_builtin("_wide"), "_wide", log)
    summary = []
    for k in IDEAS:
        a, b = std[k], wide[k]
        ok = a["verdict"] == "PASSES" and b["verdict"] == "PASSES"
        if k in FOR_WREN:
            ok = ok and a["pl"] > std[REFERENCE]["pl"] and b["pl"] > wide[REFERENCE]["pl"]
            who = "Wren"
        else:
            who = "Gareth"
        summary.append({"key": k, "name": a["name"], "for": who, "standard": a["verdict"], "wide": b["verdict"],
                        "pl": a["pl"], "pl_wide": b["pl"], "adopt": ok})
        log(f"Lab result: {a['name']} (for {who}): {a['verdict']} on 12 stocks, {b['verdict']} on 60"
            + ("  -> MEETS ITS PRE-SET BAR" if ok else ""))
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump({"ideas": IDEAS, "run": datetime.now().isoformat(timespec="seconds"), "summary": summary,
                   "reference": {"standard": std[REFERENCE]["pl"], "wide": wide[REFERENCE]["pl"],
                                 "standard_verdict": std[REFERENCE]["verdict"], "wide_verdict": wide[REFERENCE]["verdict"]}}, f, indent=1)
    return summary


if __name__ == "__main__":
    run(print)
