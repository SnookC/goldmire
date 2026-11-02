"""
Does Wren's Bollinger bounce do better with a safety-net stop-loss? (written Nov 2 2026, before testing)

Her strategy passed its tests with NO stop: she buys a dip and sells only when the price climbs back
to its 20-day average. A stop sells a trade that keeps falling. Stops can save a dip-buyer from the
occasional disaster, or sell right before the bounce. This tests the same strategy, same prices:

  * no stop (what she trades now)
  * smart stop (sized to each stock's normal swings)
  * 8%, 10% and 15% stops
(after any stop-loss sale, no buying that stock back for 24 hours, as live)

on the 12-stock list (4 years), the 60-stock list (4 years) and the 300 largest companies (5 years).

THE RULE: a stop is added only if, compared with no stop, it
  1. makes at least 5% more money on the 300 stocks over 5 years (MARGIN, added the same day after
     a test on made-up random prices let a stop "win" by 12 cents), AND
  2. makes more in that test's exam (the most recent 30%), AND
  3. makes more on at least one of the 12- and 60-stock lists.
If more than one stop qualifies, the one that makes the most on the 300 wins. Otherwise no stop.
"""
import copy
import json
import os
from datetime import datetime

import backtest
import lab

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(backtest.OUT_DIR, "stop_test.json")
MARGIN = 0.05
VARIANTS = [("no stop", None), ("smart stop", "smart"), ("8% stop", 0.08), ("10% stop", 0.10), ("15% stop", 0.15)]


def due():
    return not os.path.exists(OUT_JSON)


def run(log=print):
    base = backtest.load_strategy_file(os.path.join(HERE, "strategies", "bollinger_bounce.py"))
    sets = [("12 stocks", lambda: backtest.fetch_history("stock", "1Day", log)),
            ("60 stocks", lambda: backtest.fetch_history("stock", "1Day", log, symbols=backtest.WIDE_BASKET, tag="wide")),
            ("300 stocks", lambda: backtest.fetch_history("stock", "1Day", log, symbols=lab.universe(), tag="300",
                                                          days=lab.BIG_YEARS * 365 + 350))]
    res = {}
    log("Stop-loss test: Wren's Bollinger bounce with and without a stop, on 12, 60 and 300 stocks")
    for label, fetch in sets:
        data = fetch()
        res[label] = {}
        for name, stop in VARIANTS:
            st = copy.copy(base)
            st.stop_loss = stop
            s = backtest.test(st, "stock", data)
            s["verdict"], _ = backtest.verdict(s, None)
            res[label][name] = {k: s.get(k) for k in ("trades", "pl", "exam_pl", "win_rate", "profit_factor", "beats_random",
                                                      "max_drawdown", "avg_loss", "verdict")}
            log(f"    {label}, {name}: {s['trades']} trades, ${s['pl']:+,.2f} (exam ${s['exam_pl']:+,.2f}), "
                f"worst dip ${s['max_drawdown']:,.2f}, beats {s.get('beats_random', 0):.0%} of random")
    none = {k: res[k]["no stop"] for k in res}
    ok = []
    for name, _ in VARIANTS[1:]:
        big, big0 = res["300 stocks"][name], none["300 stocks"]
        if (big["pl"] >= big0["pl"] + abs(big0["pl"]) * MARGIN and big["pl"] > big0["pl"] and big["exam_pl"] > big0["exam_pl"]
                and any(res[k][name]["pl"] > none[k]["pl"] for k in ("12 stocks", "60 stocks"))):
            ok.append(name)
    best = max(ok, key=lambda n: res["300 stocks"][n]["pl"]) if ok else None
    verdict = f"ADD THE {best.upper()}" if best else "KEEP NO STOP"
    b0 = none["300 stocks"]
    why = (f"{best} made ${res['300 stocks'][best]['pl']:+,.2f} on 300 stocks vs ${b0['pl']:+,.2f} with no stop" if best else
           f"no stop beat every stop on the 300-stock test or its exam (no stop: ${b0['pl']:+,.2f}, exam ${b0['exam_pl']:+,.2f})")
    out = {"run": datetime.now().isoformat(timespec="seconds"), "results": res, "verdict": verdict, "why": why, "qualified": ok}
    os.makedirs(backtest.OUT_DIR, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    log(f"Stop-loss test: {verdict}. {why}")
    return out


if __name__ == "__main__":
    run(print)
