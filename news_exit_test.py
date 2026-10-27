"""
Should Wren sell on bad-news headlines, or let her Bollinger rules decide every exit?

The Proving Grounds passed her strategy WITHOUT headline selling (the replay never had it).
Live, the heroes also sell when the word list calls a headline bad news. This test runs her
strategy twice over the last DAYS days on the same 60 stocks and the same prices:

  * A: her rules only (what the Proving Grounds passed)
  * B: her rules + headline selling exactly as live: sell on a bad-news call (at the open if
       it came out overnight, at about the day's typical price if during the session), no buying
       it back for 24 hours, no buying while the news is under 3 hours old

using every real headline Alpaca's news feed has for those stocks in that time.

THE RULE (set before seeing any results, Oct 27 2026): headline selling has to earn its place.
It stays only if B makes at least KEEP_MARGIN (5%) more than A over the whole test AND also makes
more than A in the exam (the last 30% of the test, as in the Proving Grounds). Otherwise it goes:
fewer trades, fewer costs, and only the rules that were actually tested.
"""
import json
import os
from datetime import datetime, timedelta, timezone

import backtest
import news
import news_replay

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(HERE, "proving_grounds", "news_exit_test.json")
DAYS = 365
WARMUP_DAYS = 320          # her rules need 200 trading days of history first
KEEP_MARGIN = 0.05
STRATEGY = "bollinger_bounce"


def due():
    return not os.path.exists(OUT_JSON)


def _stats(trades, cut):
    n = len(trades)
    pl = sum(t["ret"] for t in trades) * backtest.TRADE_DOLLARS
    exam = sum(t["ret"] for t in trades if t["exit_t"] >= cut) * backtest.TRADE_DOLLARS
    wins = sum(1 for t in trades if t["ret"] > 0)
    return {"trades": n, "pl": round(pl, 2), "exam_pl": round(exam, 2), "win_rate": round(wins / n, 3) if n else None,
            "avg": round(sum(t["ret"] for t in trades) / n, 4) if n else None,
            "news_sales": sum(1 for t in trades if t["why"] == "bad news")}


def run(news_client, log=print, days=DAYS):
    st = backtest.load_strategy_file(os.path.join(HERE, "strategies", STRATEGY + ".py"))
    data = backtest.fetch_history("stock", "1Day", log, symbols=backtest.WIDE_BASKET, tag="wide")
    end = datetime.now(timezone.utc) - timedelta(minutes=20)
    start = end - timedelta(days=days)
    keep_from = (start - timedelta(days=WARMUP_DAYS)).isoformat()
    for sym in list(data):                                   # the last year, plus warm-up for the bands
        ser = data[sym]
        k = next((i for i, t in enumerate(ser["t"]) if t >= keep_from), len(ser["t"]))
        data[sym] = {key: ser[key][k:] for key in ("t", "o", "h", "l", "c", "v")}
        if len(data[sym]["c"]) < 60:
            data.pop(sym)
    syms = list(data)
    log(f"Headline-selling test: downloading {days} days of news for {len(syms)} stocks (this takes a while)")
    stories = news_replay.fetch_stories(news_client, syms, start, end, log, max_stories=200000)
    alarms = {}
    for s in stories:
        if news.word_alarm(s):
            t = datetime.fromisoformat(s["time"]).timestamp()
            for sym in s["symbols"]:
                if sym in data:
                    alarms.setdefault(sym, []).append(t)
    for v in alarms.values():
        v.sort()
    a_tr, b_tr = [], []
    start_s = start.isoformat()
    for sym, ser in data.items():
        a_tr += [t for t in backtest.simulate(st, ser, "stock") if t["entry_t"] >= start_s]
        b_tr += [t for t in backtest.simulate(st, ser, "stock", news=alarms.get(sym, [])) if t["entry_t"] >= start_s]
    all_t = sorted(t for ser in data.values() for t in ser["t"] if t >= start_s)
    cut = all_t[int(len(all_t) * (1 - backtest.EXAM_SHARE))] if all_t else start_s
    A, B = _stats(a_tr, cut), _stats(b_tr, cut)
    keep = B["pl"] >= A["pl"] + abs(A["pl"]) * KEEP_MARGIN and B["exam_pl"] > A["exam_pl"]
    verdict = "KEEP HEADLINE SELLING" if keep else "STOP HEADLINE SELLING"
    why = (f"her rules alone: {backtest._money(A['pl'])} on {A['trades']} trades (exam {backtest._money(A['exam_pl'])}); "
           f"with headline selling: {backtest._money(B['pl'])} on {B['trades']} trades, {B['news_sales']} of them sold on news "
           f"(exam {backtest._money(B['exam_pl'])}), $100 a trade")
    result = {"run": datetime.now(timezone.utc).isoformat(timespec="seconds"), "days": days, "stocks": len(syms),
              "stories": len(stories), "alarms": sum(len(v) for v in alarms.values()), "rules_only": A,
              "with_headlines": B, "verdict": verdict, "why": why, "keep_margin": KEEP_MARGIN}
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)
    log(f"Headline-selling test: {verdict}. {why}")
    return result


if __name__ == "__main__":
    from dotenv import load_dotenv
    from alpaca.data.historical.news import NewsClient
    load_dotenv(os.path.join(HERE, ".env"))
    run(NewsClient(os.getenv("ALPACA_API_KEY", ""), os.getenv("ALPACA_SECRET_KEY", "")), print)
