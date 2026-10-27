"""
The news replay test: on real past headlines, whose bad-news calls were right,
the word list's or FinBERT's?

For each of the last DAYS days it takes every story Alpaca's news feed has on the test
stocks (the Proving Grounds' 60-stock list plus whatever the heroes hold), and asks each
reader "is this bad news?". Then it looks at what the stock actually did next:

  * from the first price after the story (the next hourly bar's open)
  * to one trading day later (and three days later)
  * minus what the S&P 500 fund (SPY) did over the same hours, so a falling market
    doesn't make every alarm look clever

Selling on an alarm only helps if the stock then does WORSE than the market. So for each
reader: how many alarms, and how the stocks did after them on average (lower = better calls).

THE RULES (set before seeing any results, Oct 22 2026):
  * a reader needs at least MIN_ALARMS alarms to be judged
  * three rules compete: the word list, FinBERT, and "both agree"
  * the one whose alarms were followed by the lowest average next-day result wins
  * FinBERT (or "both agree") only replaces the word list if it beats it by at least
    MARGIN (0.10 percentage points a day) AND the gap is at least MIN_T standard errors
    (so it's very unlikely to be luck); otherwise the word list stays
    (the MIN_T check was added on Oct 22 2026 after a test on made-up random prices showed
    the margin alone could be passed by chance; still before any real results)
  * the winner still needs your OK before it's allowed to trigger sales

SECOND QUESTION (added Oct 22 2026, also before any results): is a story really ABOUT the
stock? Alpaca tags a story with every symbol it touches (a Lam Research story also gets
SOXX, the chip fund). The check only counts a bad-news call when the headline names the
company or its ticker (news.about). The rules:
  * at least MIN_ALARMS of the word list's calls must fail the check ("not about it")
  * selling on those calls must NOT have helped: the stock did no worse than the
    S&P 500 the next day on average (>= 0)
  * and the calls that pass the check must be at least as good as the word list's overall
  * then the check is switched on (with your OK). It means selling LESS, never more,
    which is why the bar is lower than for FinBERT.

Run it with 9_test_news_reader.bat, or Goldmire runs it by itself once FinBERT is ready
(and again each week). Results: proving_grounds/news_replay.html
"""
import bisect
import html
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import news
import finbert

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "proving_grounds")
OUT_JSON = os.path.join(OUT_DIR, "news_replay.json")
OUT_HTML = os.path.join(OUT_DIR, "news_replay.html")
DAYS = 60
MIN_ALARMS = 30
MARGIN = 0.0010
MIN_T = 2.0
ONE_DAY_BARS = 7          # regular-hours hourly bars in a trading day
THREE_DAY_BARS = 21
RERUN_DAYS = 7
MAX_STORIES = 12000


def _basket(extra=()):
    try:
        from backtest import WIDE_BASKET
    except Exception:  # noqa: BLE001
        WIDE_BASKET = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "JPM", "XOM", "UNH"]
    out = list(dict.fromkeys(list(WIDE_BASKET) + [s for s in extra if s and "/" not in s]))
    return [s for s in out if s != "SPY"]


def due():
    """True when there's no replay result yet, or it's more than RERUN_DAYS old."""
    try:
        with open(OUT_JSON, encoding="utf-8") as f:
            run = datetime.fromisoformat(json.load(f)["run"])
        with open(OUT_JSON, encoding="utf-8") as f:
            if "about_verdict" not in json.load(f):
                return True                        # made before the 'about this stock?' test existed
        return datetime.now(timezone.utc) - run > timedelta(days=RERUN_DAYS)
    except (OSError, ValueError, KeyError, TypeError):
        return True


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------
def fetch_stories(news_client, symbols, start, end, log, max_stories=MAX_STORIES):
    from alpaca.data.requests import NewsRequest
    out, seen, t = [], set(), start
    while t < end and len(out) < max_stories:
        t2 = min(end, t + timedelta(days=7))
        for i in range(0, len(symbols), 30):                 # keep each request's symbol list short
            try:
                raw = news_client.get_news(NewsRequest(symbols=",".join(symbols[i:i + 30]), start=t, end=t2, limit=3000,
                                                       exclude_contentless=False)).data.get("news", [])
            except Exception as e:  # noqa: BLE001
                log(f"News replay: couldn't download news for {t:%b %d} ({e})")
                continue
            for n in raw:
                nid = str(getattr(n, "id", ""))
                if nid in seen:
                    continue
                seen.add(nid)
                syms = list(getattr(n, "symbols", None) or [])
                head = (getattr(n, "headline", "") or "").strip()
                if not syms or not head:
                    continue
                tone, _ = news.story_tone(head, getattr(n, "summary", "") or "")
                strength = 0 if news.ROUTINE.search(head) and abs(tone) <= 2 else news.headline_strength(head)
                when = getattr(n, "created_at", None)
                out.append({"id": nid, "headline": head, "time": news._aware(when).isoformat(), "symbols": syms,
                            "tone": tone, "strength": strength, "roundup": len(syms) > news.ROUNDUP})
        t = t2
        if (end - start).days > 400 and t.month != (t - timedelta(days=7)).month and t.month in (1, 7):
            log(f"    ...news up to {t:%b %Y}: {len(out)} stories so far")
    return out


def fetch_bars(stock_data, symbols, start, end, log):
    """{symbol: ([utc timestamps], [opens], [closes])} for regular-hours hourly bars."""
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.data.enums import DataFeed
    from zoneinfo import ZoneInfo
    ny = ZoneInfo("America/New_York")
    out = {}
    for i in range(0, len(symbols), 20):
        part = symbols[i:i + 20]
        try:
            got = stock_data.get_stock_bars(StockBarsRequest(symbol_or_symbols=part, timeframe=TimeFrame.Hour, start=start, end=end,
                                                             feed=DataFeed.IEX)).data
        except Exception as e:  # noqa: BLE001
            log(f"News replay: couldn't download prices for {', '.join(part[:3])}... ({e})")
            continue
        for sym, bars in got.items():
            keep = [b for b in bars if 9 <= b.timestamp.astimezone(ny).hour <= 15 and b.timestamp.astimezone(ny).weekday() < 5]
            out[sym] = ([b.timestamp.timestamp() for b in keep], [float(b.open) for b in keep], [float(b.close) for b in keep])
    return out


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------
def _move(series, t0, nbars):
    ts, op, cl = series
    i = bisect.bisect_left(ts, t0)
    j = i + nbars - 1
    if i >= len(ts) or j >= len(ts) or op[i] <= 0:
        return None, None, None
    return cl[j] / op[i] - 1, ts[i], ts[j]


def _between(series, a, b):
    ts, op, cl = series
    i, j = bisect.bisect_left(ts, a), bisect.bisect_left(ts, b)
    if i >= len(ts) or j >= len(ts) or op[i] <= 0:
        return None
    return cl[j] / op[i] - 1


def outcomes(stories, bars, names=None):
    """One row per (story, test stock): what the stock did next, beyond the S&P 500."""
    spy = bars.get("SPY")
    rows, used = [], set()
    for st in stories:
        if st["roundup"]:
            continue
        t0 = datetime.fromisoformat(st["time"]).timestamp()
        for sym in st["symbols"]:
            if sym not in bars or sym == "SPY":
                continue
            r1, a, b = _move(bars[sym], t0, ONE_DAY_BARS)
            if r1 is None:
                continue
            m1 = _between(spy, a, b) if spy else 0.0
            r3, a3, b3 = _move(bars[sym], t0, THREE_DAY_BARS)
            m3 = _between(spy, a3, b3) if (spy and r3 is not None) else 0.0
            rows.append({"story": st["id"], "symbol": sym, "time": st["time"], "headline": st["headline"],
                         "entry": a, "adj1": r1 - (m1 or 0.0), "adj3": (r3 - (m3 or 0.0)) if r3 is not None else None,
                         "word": news.word_alarm(st), "fb": st.get("fb"), "finbert": finbert.is_alarm(st.get("fb")),
                         "about": news.about(st["headline"], sym, (names or {}).get(sym, ""))})
    return rows


def _stats(rows):
    # one call per stock per hour: several stories on the same event count once
    uniq = {}
    for r in rows:
        uniq.setdefault((r["symbol"], r["entry"]), r)
    rs = list(uniq.values())
    n = len(rs)
    if not n:
        return {"n": 0}
    a1 = sorted(r["adj1"] for r in rs)
    a3 = [r["adj3"] for r in rs if r["adj3"] is not None]
    mean = sum(a1) / n
    sd = (sum((x - mean) ** 2 for x in a1) / (n - 1)) ** 0.5 if n > 1 else 0.0
    return {"n": n, "avg1": round(mean, 5), "sd1": round(sd, 5), "median1": round(a1[n // 2], 5),
            "down1": round(sum(1 for x in a1 if x < 0) / n, 3),
            "avg3": round(sum(a3) / len(a3), 5) if a3 else None}


def judge(groups):
    """Apply the rules written at the top of this file."""
    cands = {k: groups[k] for k in ("word", "finbert", "both") if groups[k].get("n", 0) >= MIN_ALARMS}
    if "word" not in cands:
        return "TOO FEW", f"the word list made fewer than {MIN_ALARMS} bad-news calls in this period; nothing to compare yet"
    best = min(cands, key=lambda k: cands[k]["avg1"])
    w = cands["word"]["avg1"]
    if best == "word":
        return "KEEP WORD LIST", "the word list's bad-news calls were followed by the weakest prices"
    gap = w - cands[best]["avg1"]
    name = {"finbert": "FinBERT", "both": "'both agree'"}[best]
    a, b = cands["word"], cands[best]
    se = ((a["sd1"] ** 2) / a["n"] + (b["sd1"] ** 2) / b["n"]) ** 0.5
    t = gap / se if se else 0.0
    if gap < MARGIN or t < MIN_T:
        return "TOO CLOSE", (f"{name} edged out the word list by {gap:.2%} a day, but that could easily be luck "
                             f"({t:.1f} standard errors; needs {MARGIN:.2%} and {MIN_T:.0f}); the word list stays")
    return "SWITCH: " + name, f"{name}'s bad-news calls were followed by prices {gap:.2%} a day weaker than the word list's ({t:.1f} standard errors)"


def judge_about(groups):
    """The 'is it about this stock?' rules written at the top of this file."""
    out, keep, word = groups["word_not_about"], groups["word_about"], groups["word"]
    if out.get("n", 0) < MIN_ALARMS:
        return "TOO FEW", f"only {out.get('n', 0)} of the word list's calls were about a different company (needs {MIN_ALARMS})"
    if out["avg1"] < 0:
        return "DON'T ADD", (f"selling on stories about other companies still helped ({out['avg1']:+.2%} a day vs the S&P 500), "
                             "so the check would throw away useful sales")
    if keep.get("n", 0) and keep["avg1"] > word["avg1"]:
        return "DON'T ADD", "the calls that pass the check were no better than the word list's overall"
    return "ADD THE CHECK", (f"stocks the word list sold over someone else's news then did {out['avg1']:+.2%} a day vs the S&P 500 "
                             f"(selling didn't help), while calls that named the company did {keep['avg1']:+.2%}")


def run(news_client, stock_data, log=print, extra=(), days=DAYS, names=None):
    if not finbert.load_now(log):
        raise RuntimeError("FinBERT isn't available: " + finbert.status())
    end = datetime.now(timezone.utc) - timedelta(minutes=20)
    start = end - timedelta(days=days)
    syms = _basket(extra)
    log(f"News replay: downloading {days} days of news and prices for {len(syms)} stocks")
    stories = fetch_stories(news_client, syms, start, end, log)
    bars = fetch_bars(stock_data, syms + ["SPY"], start, end + timedelta(minutes=19), log)
    todo = [s for s in stories if not s["roundup"]]
    log(f"News replay: FinBERT is reading {len(todo)} headlines")
    for st, sc in zip(todo, finbert.score([s["headline"] for s in todo]) or []):
        st["fb"] = sc
    rows = outcomes(stories, bars, names)
    groups = {
        "all": _stats(rows),
        "word": _stats([r for r in rows if r["word"]]),
        "finbert": _stats([r for r in rows if r["finbert"]]),
        "both": _stats([r for r in rows if r["word"] and r["finbert"]]),
        "word_only": _stats([r for r in rows if r["word"] and not r["finbert"]]),
        "finbert_only": _stats([r for r in rows if r["finbert"] and not r["word"]]),
        "word_about": _stats([r for r in rows if r["word"] and r["about"]]),
        "word_not_about": _stats([r for r in rows if r["word"] and not r["about"]]),
    }
    verdict, why = judge(groups)
    about_verdict, about_why = judge_about(groups) if names else ("NOT RUN", "no company names to check against")

    def ex(pick, k=12):
        out = {}
        for r in sorted((r for r in rows if pick(r)), key=lambda r: r["time"], reverse=True):
            out.setdefault((r["symbol"], r["entry"]), r)
        return [{"time": r["time"][:16], "symbol": r["symbol"], "headline": r["headline"][:140], "adj1": round(r["adj1"], 4),
                 "finbert": finbert.label(r["fb"])} for r in list(out.values())[:k]]

    result = {"run": datetime.now(timezone.utc).isoformat(timespec="seconds"), "days": days, "stocks": len(syms),
              "stories": len(stories), "rated": len(rows), "groups": groups, "verdict": verdict, "why": why,
              "about_verdict": about_verdict, "about_why": about_why,
              "rules": {"min_alarms": MIN_ALARMS, "margin": MARGIN, "min_t": MIN_T, "finbert_alarm": f"bad >= {finbert.ALARM_NEG:.0%}"},
              "examples": {"word_only": ex(lambda r: r["word"] and not r["finbert"]),
                           "finbert_only": ex(lambda r: r["finbert"] and not r["word"]),
                           "not_about": ex(lambda r: r["word"] and not r["about"], 20)}}
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(_html(result))
    g = groups
    log(f"News replay: {verdict}. {why}")
    log(f"News replay, 'is it about this stock?': {about_verdict}. {about_why}")
    for k, label in (("word", "word list"), ("finbert", "FinBERT"), ("both", "both agree"), ("word_about", "names it"),
                     ("word_not_about", "other company"), ("all", "every story")):
        s = g[k]
        if s.get("n"):
            log(f"    {label:12} {s['n']:5} calls, next day {s['avg1']:+.2%} vs the S&P 500 (fell {s['down1']:.0%} of the time)")
    return result


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------
def _share(g):
    return f"{g['down1']:.0%}" if g.get("n") else ""


def _html(r):
    e = html.escape
    names = {"all": "Every story (for comparison)", "word": "Word list says bad news", "finbert": "FinBERT says bad news",
             "both": "Both agree it's bad news", "word_only": "Only the word list says bad", "finbert_only": "Only FinBERT says bad",
             "word_about": "Word list says bad, headline names the company", "word_not_about": "Word list says bad, but it's about another company"}

    def pct(x):
        return "" if x is None else f"{x:+.2%}"
    rows = "".join(f"<tr><td>{e(names[k])}</td><td>{g.get('n', 0)}</td><td class='{'neg' if (g.get('avg1') or 0) < 0 else 'pos'}'>{pct(g.get('avg1'))}</td>"
                   f"<td>{pct(g.get('median1'))}</td><td>{_share(g)}</td><td>{pct(g.get('avg3'))}</td></tr>"
                   for k, g in r["groups"].items())

    def ex(lst):
        return "".join(f"<tr><td>{e(x['time'].replace('T', ' '))}</td><td><b>{e(x['symbol'])}</b></td><td>{e(x['headline'])}</td>"
                       f"<td>{e(x['finbert'])}</td><td class='{'neg' if x['adj1'] < 0 else 'pos'}'>{x['adj1']:+.2%}</td></tr>" for x in lst) \
            or "<tr><td colspan=5>none</td></tr>"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>News Replay</title><style>
body{{font:15px/1.5 system-ui,sans-serif;margin:0;padding:20px 16px;background:#14110b;color:#efe6d2}}main{{max-width:980px;margin:auto}}
h1{{font-size:24px;margin:0 0 4px}}.v{{font-size:20px;font-weight:700;color:#e8c46a;margin:14px 0 2px}}table{{border-collapse:collapse;width:100%;margin:10px 0 22px}}
td,th{{padding:6px 8px;border-bottom:1px solid #3a3020;text-align:left;vertical-align:top}}th{{color:#b9a77f;font-weight:600}}.pos{{color:#8fd18a}}.neg{{color:#f08a7a}}
.wrap{{overflow-x:auto}}p.s{{color:#b9a77f;margin:2px 0}}</style></head><body><main>
<h1>News replay</h1><p class="s">{e(r['run'][:16].replace('T', ' '))} UTC · last {r['days']} days · {r['stocks']} stocks · {r['stories']} stories, {r['rated']} rated</p>
<div class="v">{e(r['verdict'])}</div><p>{e(r['why'])}</p>
<p class="s">"Next day" = how the stock did over the next trading day after the story, minus the S&amp;P 500. Selling on a bad-news call helps when this is negative: lower is better.</p>
<div class="wrap"><table><tr><th>Which stories</th><th>Calls</th><th>Next day</th><th>Median</th><th>Fell</th><th>3 days</th></tr>{rows}</table></div>
<h2>Is it about this stock?</h2><div class="v">{e(r.get('about_verdict', ''))}</div><p>{e(r.get('about_why', ''))}</p>
<h3>Bad-news calls about another company (the check would skip these)</h3><div class="wrap"><table><tr><th>When (UTC)</th><th></th><th>Headline</th><th>FinBERT</th><th>Next day</th></tr>{ex(r['examples'].get('not_about', []))}</table></div>
<h2>Only the word list called these bad (FinBERT disagreed)</h2><div class="wrap"><table><tr><th>When (UTC)</th><th></th><th>Headline</th><th>FinBERT</th><th>Next day</th></tr>{ex(r['examples']['word_only'])}</table></div>
<h2>Only FinBERT called these bad</h2><div class="wrap"><table><tr><th>When (UTC)</th><th></th><th>Headline</th><th>FinBERT</th><th>Next day</th></tr>{ex(r['examples']['finbert_only'])}</table></div>
<p class="s">Rules set before any results: at least {r['rules']['min_alarms']} calls to be judged; FinBERT only replaces the word list if its calls beat it by {r['rules']['margin']:.2%} a day and by at least {r['rules']['min_t']:.0f} standard errors (not luck); any switch needs your OK.</p>
</main></body></html>"""


def main():
    from dotenv import load_dotenv
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.historical.news import NewsClient
    load_dotenv(os.path.join(HERE, ".env"))
    key, secret = os.getenv("ALPACA_API_KEY", ""), os.getenv("ALPACA_SECRET_KEY", "")
    if not key or not secret or "PASTE" in key:
        raise SystemExit("Your Alpaca keys aren't set up yet (the .env file).")
    print("News replay: word list vs FinBERT on real past headlines. The first time takes a while (installing FinBERT).\n")
    from alpaca.trading.client import TradingClient
    import research
    names = {a.symbol: a.name for a in research.us_equities(TradingClient(key, secret, paper=True))}
    run(NewsClient(key, secret), StockHistoricalDataClient(key, secret), print, names=names)
    print(f"\nFull report: {OUT_HTML}")
    if "--no-open" not in sys.argv:
        import webbrowser
        webbrowser.open("file:///" + OUT_HTML.replace("\\", "/"))


if __name__ == "__main__":
    main()
