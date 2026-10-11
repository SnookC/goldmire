"""
The Hero Trials: replay each hero EXACTLY as it trades today, on real price history,
and compare it with simply buying and holding.

    python hero_test.py              every hero
    python hero_test.py wren         only heroes whose name contains "wren"

The Proving Grounds (backtest.py) asks "is this STRATEGY any good?" ($100 per trade, one
symbol at a time). The Hero Trials asks "is this HERO earning its keep?":

  * the hero's own settings from bots.json: strategy, stop-loss, "let winners build",
    take-profit, max positions (slots) and trade sizing ("risk" or "split")
  * one $100 pot shared by all its trades: a trade is only taken if a slot is free and
    there's money left, profits and losses go back into the pot
  * a wide list of busy stocks or coins (like the hero's research scan) plus its watchlist
  * a signal at a bar's close is filled at the NEXT bar's open (no peeking at the future);
    a stop is filled at the stop price, or at the open if the price gapped through it
  * trading costs on every buy and sell (0.05% stocks, 0.25% crypto, 0.2% penny)

It follows the rules of Alpaca's backtesting skill (github.com/alpacahq/alpaca-skills):
next-bar fills, costs on both sides, a buy-and-hold benchmark, the "Teaching Five"
(return vs benchmark, worst drop, trades, win rate, Sharpe vs benchmark), a data
fingerprint so runs can be compared, and every assumption written down. On top of that:
  * 4 back-to-back time windows (walk-forward): a hero should do well in most of them,
    not just one lucky stretch
  * a stress test with DOUBLE trading costs: a hero that only wins when trading is cheap
    is fragile

Writes proving_grounds/heroes.html (opens in your browser), heroes.json, and for each hero
proving_grounds/heroes/<name>/trades.csv and equity.csv. Nothing here places trades.
"""

import csv
import hashlib
import html
import json
import math
import os
import sys
import webbrowser
from datetime import datetime

import backtest
import bank
import exits

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = backtest.OUT_DIR
HERO_DIR = os.path.join(OUT_DIR, "heroes")

# A wide basket of busy, well-known names (the research scan picks from stocks like these).
WIDE = {
    "stock": ["SPY", "QQQ", "IWM", "DIA", "AAPL", "MSFT", "NVDA", "AMD", "AMZN", "GOOGL", "META", "TSLA", "JPM", "BAC",
              "WFC", "XOM", "CVX", "KO", "PEP", "WMT", "COST", "HD", "UNH", "JNJ", "PFE", "MRK", "ABBV", "V", "MA",
              "DIS", "NFLX", "INTC", "CSCO", "ORCL", "CRM", "ADBE", "AVGO", "QCOM", "MU", "PLTR", "UBER", "BA", "CAT",
              "GE", "F", "GM", "T", "VZ", "NKE", "MCD", "SOFI", "SHOP"],
    "crypto": ["BTC/USD", "ETH/USD", "SOL/USD", "DOGE/USD", "XRP/USD", "AVAX/USD", "LTC/USD", "LINK/USD", "BCH/USD",
               "UNI/USD", "AAVE/USD", "DOT/USD", "SHIB/USD"],
}
BENCHMARK = {"stock": "SPY", "penny": "SPY", "crypto": "BTC/USD"}
DAYS_PER_YEAR = {"stock": 252, "penny": 252, "crypto": 365}
WINDOWS = 4
STRESS = 2.0                      # costs multiplied by this in the stress test
MIN_TRADES = 20
DISCLOSURE = ("This is a hypothetical historical simulation, not actual trading performance. Backtested results do "
              "not guarantee future results. Results depend on data quality, fees, slippage, liquidity and execution "
              "assumptions. For research and education only; not investment advice. Goldmire trades paper money only.")


# ---------------------------------------------------------------------------
# HEROES AS THEY TRADE TODAY
# ---------------------------------------------------------------------------
def current_heroes():
    """The heroes from bots.json, with any settings updates the running bot hasn't applied yet
    (applied in memory only: this never writes bots.json)."""
    import bot
    try:
        with open(bot.BOTS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {"bots": json.loads(json.dumps(bot.DEFAULT_BOTS)), "applied_updates": []}
    done = set(data.get("applied_updates", []))
    heroes = data.get("bots", [])
    for uid, _title, changes in bot.SETTINGS_UPDATES:
        if uid in done:
            continue
        for b in heroes:
            for k, v in changes.get(b.get("name"), {}).items():
                b[k] = v
    return heroes


def hero_strategy(hero, files=None):
    """The backtest.Strategy a hero really uses, with the hero's own stop / exit / take-profit
    (the same precedence bot.py uses). Returns (strategy, market)."""
    import bot
    market = hero.get("kind", "stock")
    key = hero.get("strategy")
    if key in bot.STRATEGIES:
        fn = bot.STRATEGIES[key]
        st = backtest.Strategy(key, key, (lambda f: lambda bars: f(bars["c"]))(fn), "15Min", builtin=True)
        stop = hero.get("stop_loss", exits.DEFAULT_STOP)
        tp = hero.get("take_profit")
    else:
        files = files if files is not None else backtest.file_strategies()
        if key not in files:
            raise ValueError(f"strategy '{key}' isn't in the strategies folder")
        base = files[key]
        st = backtest.Strategy(base.key, base.name, base.signal, base.timeframe, base.markets, source=base.source,
                               rules=base.rules, lookback=base.lookback, style=base.style)
        stop = hero["stop_loss"] if "stop_loss" in hero else base.stop_loss
        tp = hero["take_profit"] if "take_profit" in hero else base.take_profit
    st.stop_loss, st.take_profit = stop, tp
    st.exit_mode = hero.get("exit", exits.DEFAULT_EXIT)
    return st, market


def universe(hero, market):
    if market == "penny":
        return None                                   # backtest.penny_basket picks today's busiest $1-$5 stocks
    extra = [s for s in hero.get("watchlist", []) if s not in WIDE[market]]
    return WIDE[market] + extra


# ---------------------------------------------------------------------------
# THE REPLAY: one pot, limited slots, trades sized like the hero sizes them
# ---------------------------------------------------------------------------
def _day(ts):
    return ts[:10]


def replay(hero, st, market, data, cost_mult=1.0):
    cost = backtest.COST[market] * cost_mult
    candidates = []
    for sym, series in data.items():
        for tr in backtest.simulate(st, series, market, cost=cost):
            tr["sym"] = sym
            candidates.append(tr)
    # every bar's close by day, to value open trades at the end of each day
    day_close = {}
    for sym, series in data.items():
        d = {}
        for t, c in zip(series["t"], series["c"]):
            d[_day(t)] = c
        day_close[sym] = d
    days = sorted({_day(t) for s in data.values() for t in s["t"]})
    # at the same moment: other trades' exits first (frees a slot), then entries, then a trade that
    # was bought and stopped out within the same bar
    events = sorted([(tr["entry_t"], 1, i) for i, tr in enumerate(candidates)] +
                    [(tr["exit_t"], 0 if tr["exit_t"] > tr["entry_t"] else 2, i) for i, tr in enumerate(candidates)])
    memory = {"bank": {}}
    acct = bank._acct(memory, {"name": hero["name"], "dollars": float(hero.get("dollars", 100))})
    acct["pot"] = start = float(hero.get("dollars", 100))
    slots = max(1, int(hero.get("max_positions", 1)))
    open_, taken, skipped, fees = {}, [], 0, 0.0
    equity, ei = [], 0

    def committed():
        return sum(p["size"] for p in open_.values())

    for day in days:
        while ei < len(events) and _day(events[ei][0]) <= day:
            _t, is_entry, i = events[ei]
            ei += 1
            tr = candidates[i]
            if is_entry:
                if len(open_) >= slots or tr["sym"] in {p["sym"] for p in open_.values()}:
                    skipped += 1
                    continue
                size = bank.slot_size(memory, hero, committed(), tr.get("risk"))
                if hero.get("sizing") != "risk":
                    size = min(size, acct["pot"] - committed())
                if size < bank.MIN_TRADE:
                    skipped += 1
                    continue
                entry_px = data[tr["sym"]]["o"][tr["entry_i"]]
                open_[i] = {"sym": tr["sym"], "size": size, "entry_px": entry_px}
            elif i in open_:
                p = open_.pop(i)
                pl = p["size"] * tr["ret"]
                fees += p["size"] * cost * 2
                acct["pot"] += pl
                taken.append({**{k: tr[k] for k in ("sym", "entry_t", "exit_t", "why", "bars")}, "size": round(p["size"], 2),
                              "pl": round(pl, 2), "ret": round(tr["ret"], 5)})
        marked = 0.0
        for p in open_.values():
            px = day_close[p["sym"]].get(day)
            if px is None:                                    # no bar that day (weekend for a stock): last known
                px = next((day_close[p["sym"]][d] for d in reversed(days[:days.index(day)]) if d in day_close[p["sym"]]), p["entry_px"])
            marked += p["size"] * ((px * (1 - cost)) / (p["entry_px"] * (1 + cost)) - 1)
        equity.append((day, round(acct["pot"] + marked, 4), round(committed(), 2)))
    return {"start": start, "equity": equity, "trades": taken, "skipped": skipped, "fees": round(fees, 2)}


def benchmark(market, data, start_money, days):
    sym = BENCHMARK[market]
    if sym not in data:
        return None
    s, cost = data[sym], backtest.COST["stock" if market == "penny" else market]
    first = s["o"][0] * (1 + cost)
    closes = {_day(t): c for t, c in zip(s["t"], s["c"])}
    out, last = [], s["c"][0]
    for d in days:
        last = closes.get(d, last)
        out.append((d, start_money * last * (1 - cost) / first, 0))
    return {"symbol": sym, "equity": out}


# ---------------------------------------------------------------------------
# NUMBERS
# ---------------------------------------------------------------------------
def metrics(equity, start, market, trades=None):
    vals = [e[1] for e in equity]
    if not vals:
        return {}
    total = vals[-1] / start - 1
    years = max(len(vals) / DAYS_PER_YEAR[market], 1e-9)
    ann = (vals[-1] / start) ** (1 / years) - 1 if vals[-1] > 0 else -1.0
    peak, dd = vals[0], 0.0
    for v in vals:
        peak = max(peak, v)
        dd = max(dd, 1 - v / peak if peak > 0 else 0)
    rets = [b / a - 1 for a, b in zip(vals[:-1], vals[1:]) if a > 0]
    if len(rets) > 2:
        mean = sum(rets) / len(rets)
        sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1))          # sample std (N-1)
        sharpe = mean / sd * math.sqrt(DAYS_PER_YEAR[market]) if sd > 0 else 0.0
    else:
        sharpe = 0.0
    m = {"final": round(vals[-1], 2), "total_return": round(total, 4), "ann_return": round(ann, 4),
         "max_drawdown": round(dd, 4), "sharpe": round(sharpe, 2), "days": len(vals),
         "from": equity[0][0], "to": equity[-1][0]}
    if trades is not None:
        pl = [t["pl"] for t in trades]
        wins, losses = [p for p in pl if p > 0], [p for p in pl if p <= 0]
        m.update({"trades": len(pl), "win_rate": round(len(wins) / len(pl), 3) if pl else 0.0,
                  "profit_factor": round(sum(wins) / -sum(losses), 2) if losses and sum(losses) < 0 else (99.0 if wins else 0.0),
                  "avg_win": round(sum(wins) / len(wins), 2) if wins else 0.0,
                  "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0.0,
                  "exposure": round(sum(e[2] for e in equity) / max(1e-9, sum(e[1] for e in equity)), 3)})
    return m


def windows(equity, bench, n=WINDOWS):
    """Return in each of n back-to-back stretches of time, hero vs benchmark."""
    out = []
    size = len(equity) // n
    if size < 5:
        return out
    for k in range(n):
        a, b = k * size, (len(equity) - 1 if k == n - 1 else (k + 1) * size)
        hr = equity[b][1] / equity[a][1] - 1 if equity[a][1] > 0 else 0.0
        br = bench[b][1] / bench[a][1] - 1 if bench and bench[a][1] > 0 else None
        out.append({"from": equity[a][0], "to": equity[b][0], "hero": round(hr, 4), "bench": None if br is None else round(br, 4)})
    return out


def judge(m, bm, wins, stress_return):
    """(verdict, plain-words reason)"""
    if m.get("trades", 0) < MIN_TRADES:
        return "TOO FEW", f"only {m.get('trades', 0)} trades in the test: not enough to judge either way"
    if m["total_return"] <= 0:
        return "LOSING", "lost money over the test, after trading costs"
    up = sum(1 for w in wins if w["hero"] > 0)
    fragile = stress_return is not None and stress_return <= 0
    beats = bm is not None and (m["sharpe"] > bm["sharpe"] or
                                (m["total_return"] > 0 and m["max_drawdown"] < bm["max_drawdown"] * 0.5
                                 and m["sharpe"] >= bm["sharpe"] * 0.8))
    if beats and up >= WINDOWS - 1 and not fragile:
        return "EARNING", (f"made money in {up} of {len(wins)} stretches, survives double trading costs, and beats "
                           "buying and holding for the risk taken")
    reasons = []
    if not beats:
        reasons.append("doesn't beat simply buying and holding for the risk taken")
    if up < WINDOWS - 1:
        reasons.append(f"made money in only {up} of {len(wins)} stretches")
    if fragile:
        reasons.append("loses money if trading costs double (fragile)")
    return "SO-SO", "profitable, but " + "; ".join(reasons)


def fingerprint(data):
    h = hashlib.sha256()
    for sym in sorted(data):
        s = data[sym]
        h.update(f"{sym}|{len(s['t'])}|{s['t'][0]}|{s['t'][-1]}|{s['c'][0]:.6f}|{s['c'][-1]:.6f}".encode())
    return h.hexdigest()[:16]


# ---------------------------------------------------------------------------
# RUN + REPORT
# ---------------------------------------------------------------------------
def run(only=None, log=print, fetch=backtest.fetch_history):
    heroes = current_heroes()
    if only:
        heroes = [h for h in heroes if only.lower() in (h.get("hero", "") + " " + h.get("name", "")).lower()]
    files = backtest.file_strategies(log)
    cache, results = {}, []
    for hero in heroes:
        label = f"{hero.get('hero', hero['name'])} ({hero['name']})"
        try:
            st, market = hero_strategy(hero, files)
        except ValueError as e:
            log(f"{label}: skipped, {e}")
            continue
        syms = universe(hero, market)
        key = (market, st.timeframe, tuple(syms or ()))
        if key not in cache:
            try:
                tag = "" if market == "penny" else "_wide"
                cache[key] = fetch(market, st.timeframe, log, symbols=syms, tag=tag)
            except SystemExit:
                raise
            except Exception as e:  # noqa: BLE001
                log(f"Couldn't download {market} {st.timeframe} prices ({e})")
                cache[key] = {}
        data = cache[key]
        if not data:
            continue
        if market == "penny" and "SPY" not in data:          # penny heroes are compared with the stock market
            try:
                data = {**data, **fetch("stock", st.timeframe, log, symbols=["SPY"], tag="_spy")}
            except Exception:  # noqa: BLE001
                pass
        trade_data = {k: v for k, v in data.items() if not (market == "penny" and k == "SPY")}
        log(f"{label}: replaying {len(trade_data)} symbols, {st.timeframe} bars...")
        res = replay(hero, st, market, trade_data)
        stressed = replay(hero, st, market, trade_data, cost_mult=STRESS)
        days = [e[0] for e in res["equity"]]
        bench = benchmark(market, data, res["start"], days)
        m = metrics(res["equity"], res["start"], market, res["trades"])
        bm = metrics(bench["equity"], res["start"], market) if bench else None
        sm = metrics(stressed["equity"], res["start"], market, stressed["trades"])
        wins = windows(res["equity"], bench["equity"] if bench else None)
        verdict, why = judge(m, bm, wins, sm.get("total_return"))
        r = {"name": hero["name"], "hero": hero.get("hero", hero["name"]), "market": market, "strategy": hero.get("strategy"),
             "timeframe": st.timeframe, "settings": {"stop_loss": st.stop_loss, "exit": st.exit_mode, "take_profit": st.take_profit,
                                                      "max_positions": hero.get("max_positions"), "sizing": hero.get("sizing", "split"),
                                                      "dollars": hero.get("dollars", 100)},
             "symbols": len(trade_data), "fingerprint": fingerprint(trade_data), "benchmark": bench and bench["symbol"],
             "hero_m": m, "bench_m": bm, "stress_m": sm, "windows": wins, "skipped": res["skipped"], "fees": res["fees"],
             "verdict": verdict, "why": why,
             "first_trade": res["trades"][0] if res["trades"] else None, "last_trade": res["trades"][-1] if res["trades"] else None}
        results.append(r)
        _write_hero_files(r, res, bench)
        log(f"  {verdict}: {_pct(m['total_return'])} vs {bench and bench['symbol']} {_pct(bm['total_return']) if bm else 'n/a'}, "
            f"worst drop {_pct(-m['max_drawdown'])}, {m['trades']} trades, {m['win_rate']:.0%} wins, Sharpe {m['sharpe']:.2f}"
            + (f" vs {bm['sharpe']:.2f}" if bm else ""))
    report = {"run": datetime.now().isoformat(timespec="seconds"), "costs": backtest.COST, "stress": STRESS,
              "results": results, "disclosure": DISCLOSURE}
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "heroes.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    with open(os.path.join(OUT_DIR, "heroes.html"), "w", encoding="utf-8") as f:
        f.write(render_html(report))
    return report


def _write_hero_files(r, res, bench):
    d = os.path.join(HERO_DIR, r["name"])
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "trades.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "bought", "sold", "why sold", "dollars", "profit", "return"])
        for t in res["trades"]:
            w.writerow([t["sym"], t["entry_t"], t["exit_t"], t["why"], t["size"], t["pl"], t["ret"]])
    bmap = {e[0]: e[1] for e in (bench["equity"] if bench else [])}
    with open(os.path.join(d, "equity.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["day", "hero", "in trades", bench["symbol"] + " buy and hold" if bench else "benchmark"])
        for day, v, inv in res["equity"]:
            w.writerow([day, round(v, 2), inv, round(bmap.get(day, 0), 2)])


def _usd(v):
    return f"{'-' if v < 0 else ''}${abs(v):,.2f}"


def _pct(v):
    return f"{v:+.1%}"


def _spark(equity, bench, w=220, h=44):
    vals = [e[1] for e in equity]
    bvals = [e[1] for e in bench] if bench else []
    allv = vals + bvals
    if len(vals) < 2:
        return ""
    lo, hi = min(allv), max(allv)
    span = hi - lo or 1

    def path(v):
        return " ".join(f"{i * w / (len(v) - 1):.1f},{h - (x - lo) / span * h:.1f}" for i, x in enumerate(v))
    b = f'<polyline points="{path(bvals)}" fill="none" stroke="#a9a48f" stroke-width="1.2" stroke-dasharray="3 3" vector-effect="non-scaling-stroke"/>' if len(bvals) > 1 else ""
    return (f'<svg width="100%" height="{h * 2}" viewBox="0 0 {w} {h}" preserveAspectRatio="none" role="img" aria-label="hero vs buy and hold">{b}'
            f'<polyline points="{path(vals)}" fill="none" stroke="#e2b65c" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>')


def render_html(report):
    e = html.escape
    cards = []
    for r in report["results"]:
        m, bm, sm = r["hero_m"], r["bench_m"] or {}, r["stress_m"]
        cls = {"EARNING": "up", "SO-SO": "mid", "LOSING": "dn", "TOO FEW": "mid"}[r["verdict"]]
        wrows = "".join(f'<tr><td>{e(w["from"])} → {e(w["to"])}</td><td class="n {"up" if w["hero"] > 0 else "dn"}">{_pct(w["hero"])}</td>'
                        f'<td class="n">{"" if w["bench"] is None else _pct(w["bench"])}</td></tr>' for w in r["windows"])
        s = r["settings"]
        stop = exits.describe(s["stop_loss"], s["exit"]) + (f", sells at +{s['take_profit']:.0%}" if s["take_profit"] else "")
        ft, lt = r["first_trade"], r["last_trade"]
        heq = _load_equity(r["name"])
        cards.append(f"""<section class="card">
<div class="head"><h2>{e(r['hero'])}</h2><span class="v {cls}">{e(r['verdict'])}</span></div>
<p class="why">{e(r['why'])}</p>
{_spark(*heq)}
<p class="src">gold = {e(r['hero'])}, dashed = ${s['dollars']} in {e(r['benchmark'] or '-')} bought and held</p>
<table><thead><tr><th></th><th class="n">{e(r['hero'].split()[0])}</th><th class="n">Buy &amp; hold {e(r['benchmark'] or '')}</th></tr></thead><tbody>
<tr><td>1. Total return</td><td class="n {'up' if m['total_return'] > 0 else 'dn'}">{_pct(m['total_return'])}</td><td class="n">{_pct(bm['total_return']) if bm else ''}</td></tr>
<tr><td>2. Worst drop</td><td class="n">{_pct(-m['max_drawdown'])}</td><td class="n">{_pct(-bm['max_drawdown']) if bm else ''}</td></tr>
<tr><td>3. Trades</td><td class="n">{m['trades']}</td><td class="n">1</td></tr>
<tr><td>4. Win rate</td><td class="n">{m['win_rate']:.0%}</td><td class="n"></td></tr>
<tr><td>5. Sharpe <span class="src">(return per unit of bumpiness)</span></td><td class="n">{m['sharpe']:.2f}</td><td class="n">{bm.get('sharpe', 0):.2f}</td></tr>
<tr><td>Yearly pace</td><td class="n">{_pct(m['ann_return'])}</td><td class="n">{_pct(bm['ann_return']) if bm else ''}</td></tr>
<tr><td>Profit factor <span class="src">($ won per $1 lost)</span></td><td class="n">{m['profit_factor']:.2f}</td><td></td></tr>
<tr><td>Average win / loss</td><td class="n">{_usd(m['avg_win'])} / {_usd(m['avg_loss'])}</td><td></td></tr>
<tr><td>Money in trades <span class="src">(average)</span></td><td class="n">{m['exposure']:.0%}</td><td class="n">100%</td></tr>
<tr><td>Trading costs paid</td><td class="n">${r['fees']:.2f}</td><td></td></tr>
<tr><td>Signals skipped <span class="src">(slots full or pot spent)</span></td><td class="n">{r['skipped']}</td><td></td></tr>
<tr><td>Stress test: costs doubled</td><td class="n {'up' if sm.get('total_return', 0) > 0 else 'dn'}">{_pct(sm.get('total_return', 0))}</td><td></td></tr>
</tbody></table>
<h3>Four stretches of time</h3>
<table><thead><tr><th>Stretch</th><th class="n">Hero</th><th class="n">Buy &amp; hold</th></tr></thead><tbody>{wrows}</tbody></table>
<p class="src">{e(r['strategy'])} on {e(r['timeframe'])} bars · {stop} · {s['max_positions']} slots · sizing: {e(s['sizing'])} ·
{r['symbols']} symbols · {e(m['from'])} to {e(m['to'])} · data fingerprint {e(r['fingerprint'])}<br>
First trade: {e(_tr(ft))}<br>Last trade: {e(_tr(lt))}<br>
Every trade: heroes/{e(r['name'])}/trades.csv · day by day: heroes/{e(r['name'])}/equity.csv</p>
</section>""")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>The Hero Trials</title><style>
:root{{--bg:#11160f;--panel:#182016;--ink:#efe6cf;--muted:#a9a48f;--gilt:#e2b65c;--up:#7fc46a;--dn:#e07a5f}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,sans-serif;padding:20px 16px}}
h1,h2,h3{{font-family:Georgia,serif;color:var(--gilt);margin:0}} h1{{margin-bottom:6px}} h3{{font-size:16px;margin:14px 0 4px}}
p{{color:var(--muted);max-width:75ch}} .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:16px;margin-top:16px}}
.card{{background:var(--panel);border-radius:12px;padding:16px}} .head{{display:flex;justify-content:space-between;align-items:center;gap:8px}}
.why{{color:var(--ink);margin:6px 0 10px}} table{{border-collapse:collapse;width:100%}} td,th{{padding:5px 6px;border-bottom:1px solid #2c3628;text-align:left}}
th{{color:var(--muted);font-weight:600;font-size:13px}} .n{{text-align:right;font-variant-numeric:tabular-nums}} .src{{color:var(--muted);font-size:12px}}
.up{{color:var(--up)}} .dn{{color:var(--dn)}} .mid{{color:var(--gilt)}} .v{{font-weight:700;font-size:13px;border:1px solid currentColor;border-radius:999px;padding:2px 10px}}
svg{{display:block;max-width:100%;margin:6px 0 0}}</style></head><body>
<h1>The Hero Trials</h1>
<p>Tested {e(report['run'].replace('T', ' at '))}. Each hero replayed exactly as it trades today (its strategy, stops, slots, sizing and one ${100} pot)
on real price history, and compared with simply buying and holding. Trading costs on every buy and sell; the stress test doubles them.
Verdicts: <b class="up">EARNING</b> beats buy-and-hold for the risk, makes money in most stretches and survives double costs ·
<b class="mid">SO-SO</b> profitable but not clearly worth it · <b class="dn">LOSING</b> · <b class="mid">TOO FEW</b> trades to judge.</p>
<div class="grid">{''.join(cards)}</div>
<h3>What this test can't see</h3>
<p>Bad-news exits and the Town Crier; heroes sharing symbols with each other; the exact 5-minute checking rhythm (decisions use completed bars);
fills at the open may be worse in fast markets. The stock list is today's busy names, and the penny list is today's busiest $1&ndash;$5 stocks:
companies that crashed or vanished are missing (survivorship bias), which flatters results, especially for pennies.</p>
<p class="src">{e(report['disclosure'])}</p></body></html>"""


def _tr(t):
    if not t:
        return "none"
    return f"{t['sym']} bought {t['entry_t'][:16].replace('T', ' ')}, sold {t['exit_t'][:16].replace('T', ' ')} ({t['why']}), {'+' if t['pl'] >= 0 else '-'}${abs(t['pl']):.2f}"


def _load_equity(name):
    path = os.path.join(HERO_DIR, name, "equity.csv")
    hero, bench = [], []
    try:
        with open(path, encoding="utf-8") as f:
            rows = list(csv.reader(f))[1:]
        step = max(1, len(rows) // 200)
        for row in rows[::step]:
            hero.append((row[0], float(row[1])))
            if float(row[3]) > 0:
                bench.append((row[0], float(row[3])))
    except (OSError, ValueError, IndexError):
        pass
    return hero, bench


def main():
    only = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else None
    print("The Hero Trials: replaying every hero exactly as it trades today. This takes a few minutes.\n")
    report = run(only)
    path = os.path.join(OUT_DIR, "heroes.html")
    print(f"\nFull report: {path}")
    if "--no-open" not in sys.argv:
        webbrowser.open("file:///" + path.replace("\\", "/"))


if __name__ == "__main__":
    main()
